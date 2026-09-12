from web3 import Web3
from app.services.merkle import build_merkle_tree, get_merkle_proof
import os

w3 = Web3(Web3.HTTPProvider("https://rpc-amoy.polygon.technology"))
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "0xYourDeployedAddress")
CONTRACT_ABI = [
    {
        "inputs": [{"internalType": "bytes32", "name": "merkleRoot", "type": "bytes32"}],
        "name": "anchorHash",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "merkleRoot", "type": "bytes32"}],
        "name": "isAnchored",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    }
]

try:
    contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)
except Exception:
    contract = None

def anchor_pending_documents(db):
    pending = db.execute(
        "SELECT id, sha256_hash FROM documents WHERE merkle_root IS NULL"
    ).fetchall()

    if not pending:
        return {"anchored": 0}

    leaves = [row["sha256_hash"] for row in pending]
    root, levels = build_merkle_tree(leaves)

    private_key = os.getenv("PRIVATE_KEY", "YOUR_PRIVATE_KEY")
    account = w3.eth.account.from_key(private_key)
    
    tx = contract.functions.anchorHash(bytes.fromhex(root)).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 100000,
    })
    
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash)

    # Store root + proof-relevant data back on each document
    for i, row in enumerate(pending):
        db.execute(
            "UPDATE documents SET merkle_root = %s, blockchain_tx_hash = %s WHERE id = %s",
            (root, tx_hash.hex(), row["id"]),
        )
    db.commit()

    return {"anchored": len(pending), "root": root, "tx_hash": tx_hash.hex()}
