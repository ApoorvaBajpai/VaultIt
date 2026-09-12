import hashlib

def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()

def build_merkle_tree(leaves: list[str]) -> tuple[str, list[list[str]]]:
    """Returns (root_hash, all_tree_levels) so we can generate proofs later."""
    if not leaves:
        raise ValueError("No leaves to anchor")

    levels = [leaves]
    current = leaves

    while len(current) > 1:
        next_level = []
        for i in range(0, len(current), 2):
            left = current[i]
            right = current[i + 1] if i + 1 < len(current) else left  # duplicate last if odd
            next_level.append(sha256_hex(left + right))
        levels.append(next_level)
        current = next_level

    return current[0], levels

def get_merkle_proof(levels: list[list[str]], leaf_index: int) -> list[str]:
    """Returns the sibling hashes needed to prove a leaf is in the tree."""
    proof = []
    index = leaf_index
    for level in levels[:-1]:
        sibling_index = index + 1 if index % 2 == 0 else index - 1
        if sibling_index < len(level):
            proof.append(level[sibling_index])
        index //= 2
    return proof

def verify_proof(leaf: str, proof: list[str], root: str, leaf_index: int) -> bool:
    current = leaf
    index = leaf_index
    for sibling in proof:
        if index % 2 == 0:
            current = sha256_hex(current + sibling)
        else:
            current = sha256_hex(sibling + current)
        index //= 2
    return current == root
