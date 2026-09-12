const hre = require("hardhat");

async function main() {
    const HashAnchor = await hre.ethers.getContractFactory("HashAnchor");
    const contract = await HashAnchor.deploy();
    await contract.waitForDeployment();
    console.log("Deployed to:", await contract.getAddress());
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
