require("@nomicfoundation/hardhat-toolbox");

module.exports = {
    solidity: "0.8.19",
    networks: {
        amoy: {
            url: "https://rpc-amoy.polygon.technology",
            accounts: process.env.PRIVATE_KEY ? [process.env.PRIVATE_KEY] : [],
        },
    },
};
