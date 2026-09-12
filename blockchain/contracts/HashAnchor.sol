// contracts/HashAnchor.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract HashAnchor {
    event RootAnchored(bytes32 indexed merkleRoot, uint256 timestamp, address anchoredBy);

    mapping(bytes32 => uint256) public anchoredRoots; // root => block timestamp

    function anchorHash(bytes32 merkleRoot) public {
        require(anchoredRoots[merkleRoot] == 0, "Root already anchored");
        anchoredRoots[merkleRoot] = block.timestamp;
        emit RootAnchored(merkleRoot, block.timestamp, msg.sender);
    }

    function isAnchored(bytes32 merkleRoot) public view returns (bool) {
        return anchoredRoots[merkleRoot] != 0;
    }
}
