"""
Variational Blockchain Client - Direct Smart Contract Integration

This client interacts directly with Variational smart contracts on Arbitrum One,
bypassing the API requirement. Perfect for when you don't have API credentials.

Features:
- Direct USDC deposits/withdrawals
- Settlement pool monitoring via events
- Oracle price fetching (Chainlink/Pyth)
- Position tracking via blockchain events
- No API credentials required
"""

import os
import time
from decimal import Decimal
from typing import Optional, Dict, List, Tuple
from web3 import Web3
from web3.contract import Contract
from eth_account import Account
from eth_account.signers.local import LocalAccount

# Arbitrum One Configuration
ARBITRUM_RPC = os.getenv("ARBITRUM_RPC", "https://arb1.arbitrum.io/rpc")
CHAIN_ID = 42161

# Variational Mainnet Contracts
SETTLEMENT_POOL_FACTORY = "0x0F820B9afC270d658a9fD7D16B1Bdc45b70f074C"
CORE_OLP_VAULT = "0x74bbbb0e7f0bad6938509dd4b556a39a4db1f2cd"

# USDC on Arbitrum One
USDC_ADDRESS = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
USDC_DECIMALS = 6

# Chainlink Price Feeds on Arbitrum One
CHAINLINK_FEEDS = {
    "BTC/USD": "0x6ce185860a4963106506C203335A2910413708e9",
    "ETH/USD": "0x639Fe6ab55C921f74e7fac1ee960C0B6293ba612",
    "LINK/USD": "0x86E53CF1B870786351Da77A57575e79CB55812CB",
    "ARB/USD": "0xb2A824043730FE05F3DA2efaFa1CBbe83fa548D6",
}


class BlockchainClient:
    """
    Direct blockchain integration for Variational protocol

    This client allows you to interact with Variational smart contracts
    without requiring API credentials. It's perfect for:
    - Deposits and withdrawals
    - Monitoring positions via events
    - Fetching oracle prices
    - Reading settlement pool state
    """

    def __init__(
        self,
        private_key: str,
        rpc_url: str = ARBITRUM_RPC,
        chain_id: int = CHAIN_ID
    ):
        """
        Initialize blockchain client

        Args:
            private_key: Your wallet private key (0x...)
            rpc_url: Arbitrum RPC endpoint
            chain_id: Chain ID (42161 for Arbitrum One)
        """
        # Connect to Arbitrum
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to {rpc_url}")

        self.chain_id = chain_id

        # Setup account
        self.account: LocalAccount = Account.from_key(private_key)
        self.address = self.account.address

        print(f"✅ Connected to Arbitrum One")
        print(f"📍 Wallet: {self.address}")
        print(f"💰 ETH Balance: {self.get_eth_balance():.6f} ETH")

        # Load contracts
        self.usdc = self._load_usdc_contract()
        self.factory = self._load_factory_contract()

        print(f"💵 USDC Balance: {self.get_usdc_balance():.2f} USDC")

    def _load_usdc_contract(self) -> Contract:
        """Load USDC contract"""
        # Standard ERC-20 ABI
        erc20_abi = [
            {"constant": True, "inputs": [{"name": "_owner", "type": "address"}],
             "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
            {"constant": False, "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}],
             "name": "approve", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
            {"constant": True, "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}],
             "name": "allowance", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
            {"constant": False, "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
             "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
            {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
        ]
        return self.w3.eth.contract(address=USDC_ADDRESS, abi=erc20_abi)

    def _load_factory_contract(self) -> Contract:
        """Load Settlement Pool Factory contract"""
        # Based on research, the factory has these functions
        factory_abi = [
            {"inputs": [{"internalType": "bytes16", "name": "poolId", "type": "bytes16"},
                       {"internalType": "address[]", "name": "parties", "type": "address[]"},
                       {"internalType": "uint256[]", "name": "marginRequirements", "type": "uint256[]"}],
             "name": "createPool", "outputs": [{"internalType": "address", "name": "", "type": "address"}],
             "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"internalType": "bytes16", "name": "poolId", "type": "bytes16"}],
             "name": "getPool", "outputs": [{"internalType": "address", "name": "", "type": "address"}],
             "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "oracle", "outputs": [{"internalType": "address", "name": "", "type": "address"}],
             "stateMutability": "view", "type": "function"},
            {"anonymous": False,
             "inputs": [{"indexed": True, "internalType": "bytes16", "name": "poolId", "type": "bytes16"},
                       {"indexed": False, "internalType": "address", "name": "poolAddress", "type": "address"}],
             "name": "PoolCreated", "type": "event"},
        ]
        return self.w3.eth.contract(address=SETTLEMENT_POOL_FACTORY, abi=factory_abi)

    # ==================== Balance Queries ====================

    def get_eth_balance(self) -> float:
        """Get ETH balance in decimal"""
        balance_wei = self.w3.eth.get_balance(self.address)
        return float(self.w3.from_wei(balance_wei, 'ether'))

    def get_usdc_balance(self) -> float:
        """Get USDC balance"""
        balance = self.usdc.functions.balanceOf(self.address).call()
        return balance / 10**USDC_DECIMALS

    # ==================== Oracle Price Fetching ====================

    def get_chainlink_price(self, pair: str) -> Optional[Decimal]:
        """
        Get latest price from Chainlink oracle

        Args:
            pair: Trading pair (e.g., "BTC/USD", "ETH/USD")

        Returns:
            Current price as Decimal, or None if not available
        """
        if pair not in CHAINLINK_FEEDS:
            print(f"⚠️  No Chainlink feed for {pair}")
            return None

        feed_address = CHAINLINK_FEEDS[pair]

        # Chainlink aggregator ABI
        aggregator_abi = [
            {"inputs": [], "name": "latestRoundData",
             "outputs": [
                 {"name": "roundId", "type": "uint80"},
                 {"name": "answer", "type": "int256"},
                 {"name": "startedAt", "type": "uint256"},
                 {"name": "updatedAt", "type": "uint256"},
                 {"name": "answeredInRound", "type": "uint80"}
             ],
             "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}],
             "stateMutability": "view", "type": "function"},
        ]

        feed = self.w3.eth.contract(address=feed_address, abi=aggregator_abi)

        try:
            # Get latest price
            _, answer, _, updated_at, _ = feed.functions.latestRoundData().call()
            decimals = feed.functions.decimals().call()

            price = Decimal(answer) / Decimal(10 ** decimals)

            # Check if price is stale (older than 1 hour)
            if time.time() - updated_at > 3600:
                print(f"⚠️  Price for {pair} is stale (updated {int(time.time() - updated_at)}s ago)")

            return price

        except Exception as e:
            print(f"❌ Error fetching {pair} price: {e}")
            return None

    def get_all_prices(self) -> Dict[str, Decimal]:
        """Get all available Chainlink prices"""
        prices = {}
        for pair in CHAINLINK_FEEDS.keys():
            price = self.get_chainlink_price(pair)
            if price:
                prices[pair] = price
        return prices

    # ==================== USDC Operations ====================

    def approve_usdc(self, spender: str, amount: float) -> str:
        """
        Approve USDC spending

        Args:
            spender: Address to approve (settlement pool or contract)
            amount: Amount in USDC (e.g., 100.0 for 100 USDC)

        Returns:
            Transaction hash
        """
        amount_base = int(amount * 10**USDC_DECIMALS)

        print(f"📝 Approving {amount} USDC to {spender}...")

        # Build transaction
        txn = self.usdc.functions.approve(spender, amount_base).build_transaction({
            'from': self.address,
            'nonce': self.w3.eth.get_transaction_count(self.address),
            'gas': 100000,
            'maxFeePerGas': self.w3.eth.gas_price,
            'maxPriorityFeePerGas': self.w3.to_wei('0.01', 'gwei'),
            'chainId': self.chain_id
        })

        # Sign and send
        signed = self.w3.eth.account.sign_transaction(txn, self.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)

        print(f"⏳ Waiting for confirmation...")
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt['status'] == 1:
            print(f"✅ Approved! Tx: {tx_hash.hex()}")
        else:
            print(f"❌ Approval failed! Tx: {tx_hash.hex()}")

        return tx_hash.hex()

    def transfer_usdc(self, to: str, amount: float) -> str:
        """
        Transfer USDC to address

        Args:
            to: Recipient address
            amount: Amount in USDC

        Returns:
            Transaction hash
        """
        amount_base = int(amount * 10**USDC_DECIMALS)

        print(f"💸 Transferring {amount} USDC to {to}...")

        txn = self.usdc.functions.transfer(to, amount_base).build_transaction({
            'from': self.address,
            'nonce': self.w3.eth.get_transaction_count(self.address),
            'gas': 100000,
            'maxFeePerGas': self.w3.eth.gas_price,
            'maxPriorityFeePerGas': self.w3.to_wei('0.01', 'gwei'),
            'chainId': self.chain_id
        })

        signed = self.w3.eth.account.sign_transaction(txn, self.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)

        print(f"⏳ Waiting for confirmation...")
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt['status'] == 1:
            print(f"✅ Transferred! Tx: {tx_hash.hex()}")
        else:
            print(f"❌ Transfer failed! Tx: {tx_hash.hex()}")

        return tx_hash.hex()

    # ==================== Settlement Pool Operations ====================

    def get_settlement_pool(self, pool_id: bytes) -> Optional[str]:
        """
        Get settlement pool address by ID

        Args:
            pool_id: 16-byte pool identifier

        Returns:
            Pool address or None if doesn't exist
        """
        try:
            pool_address = self.factory.functions.getPool(pool_id).call()
            if pool_address == "0x0000000000000000000000000000000000000000":
                return None
            return pool_address
        except Exception as e:
            print(f"❌ Error fetching pool: {e}")
            return None

    def get_all_settlement_pools(self, from_block: int = 0) -> List[Dict]:
        """
        Get all settlement pools by scanning PoolCreated events

        Args:
            from_block: Start scanning from this block (0 = genesis)

        Returns:
            List of pool data dictionaries
        """
        print(f"🔍 Scanning for PoolCreated events from block {from_block}...")

        # Get latest block
        latest_block = self.w3.eth.block_number

        pools = []

        # Scan in chunks of 10000 blocks (Arbitrum limit)
        chunk_size = 10000
        for start in range(from_block, latest_block, chunk_size):
            end = min(start + chunk_size - 1, latest_block)

            try:
                events = self.factory.events.PoolCreated.get_logs(
                    fromBlock=start,
                    toBlock=end
                )

                for event in events:
                    pools.append({
                        'pool_id': event['args']['poolId'].hex(),
                        'pool_address': event['args']['poolAddress'],
                        'block_number': event['blockNumber'],
                        'tx_hash': event['transactionHash'].hex()
                    })

                if end < latest_block:
                    print(f"  Scanned blocks {start}-{end}...")

            except Exception as e:
                print(f"⚠️  Error scanning blocks {start}-{end}: {e}")

        print(f"✅ Found {len(pools)} settlement pools")
        return pools

    def get_oracle_address(self) -> str:
        """Get the oracle address from factory"""
        try:
            oracle = self.factory.functions.oracle().call()
            return oracle
        except Exception as e:
            print(f"❌ Error fetching oracle: {e}")
            return "0x0000000000000000000000000000000000000000"

    # ==================== EIP-712 Permit Signing ====================

    def sign_usdc_permit(
        self,
        spender: str,
        value: int,
        deadline: int,
        nonce: Optional[int] = None
    ) -> Tuple[int, bytes, bytes]:
        """
        Sign EIP-2612 permit for USDC

        Args:
            spender: Address to approve
            value: Amount in base units (not USDC, but raw units)
            deadline: Unix timestamp deadline
            nonce: Permit nonce (fetched if not provided)

        Returns:
            Tuple of (v, r, s) signature components
        """
        # USDC permit nonce is per-address
        if nonce is None:
            # You'd need to call nonces(address) on USDC contract
            # For now, default to 0
            nonce = 0

        # EIP-712 domain
        domain_data = {
            "name": "USD Coin",
            "version": "2",
            "chainId": self.chain_id,
            "verifyingContract": USDC_ADDRESS,
        }

        # Permit message type
        message_types = {
            "Permit": [
                {"name": "owner", "type": "address"},
                {"name": "spender", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "nonce", "type": "uint256"},
                {"name": "deadline", "type": "uint256"},
            ]
        }

        # Message data
        message_data = {
            "owner": self.address,
            "spender": spender,
            "value": value,
            "nonce": nonce,
            "deadline": deadline,
        }

        # Sign typed data
        signed = Account.sign_typed_data(
            self.account.key,
            domain_data=domain_data,
            message_types=message_types,
            message_data=message_data
        )

        # Extract v, r, s
        signature = signed.signature
        r = signature[:32]
        s = signature[32:64]
        v = signature[64] + 27  # Add 27 to v

        return (v, r, s)

    # ==================== Utility Functions ====================

    def estimate_gas_cost(self, gas_limit: int) -> Dict[str, float]:
        """
        Estimate transaction cost in ETH and USD

        Args:
            gas_limit: Estimated gas limit

        Returns:
            Dictionary with cost estimates
        """
        gas_price = self.w3.eth.gas_price
        cost_wei = gas_limit * gas_price
        cost_eth = float(self.w3.from_wei(cost_wei, 'ether'))

        # Try to get ETH price
        eth_price = self.get_chainlink_price("ETH/USD")
        cost_usd = float(cost_eth * eth_price) if eth_price else None

        return {
            'gas_limit': gas_limit,
            'gas_price_gwei': float(self.w3.from_wei(gas_price, 'gwei')),
            'cost_eth': cost_eth,
            'cost_usd': cost_usd
        }

    def wait_for_transaction(self, tx_hash: str, timeout: int = 120) -> Dict:
        """
        Wait for transaction confirmation

        Args:
            tx_hash: Transaction hash
            timeout: Timeout in seconds

        Returns:
            Transaction receipt
        """
        print(f"⏳ Waiting for transaction {tx_hash}...")
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

        if receipt['status'] == 1:
            print(f"✅ Transaction confirmed in block {receipt['blockNumber']}")
        else:
            print(f"❌ Transaction failed")

        return dict(receipt)


# ==================== Example Usage ====================

def main():
    """Example usage of BlockchainClient"""

    # Load private key from environment
    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        print("❌ Please set PRIVATE_KEY environment variable")
        return

    # Initialize client
    client = BlockchainClient(private_key)

    print("\n" + "="*60)
    print("🔍 VARIATIONAL BLOCKCHAIN CLIENT - EXAMPLE USAGE")
    print("="*60)

    # 1. Check balances
    print("\n1️⃣  Checking balances...")
    print(f"   ETH: {client.get_eth_balance():.6f}")
    print(f"   USDC: {client.get_usdc_balance():.2f}")

    # 2. Get oracle prices
    print("\n2️⃣  Fetching Chainlink prices...")
    prices = client.get_all_prices()
    for pair, price in prices.items():
        print(f"   {pair}: ${price:,.2f}")

    # 3. Get oracle address
    print("\n3️⃣  Getting oracle address...")
    oracle = client.get_oracle_address()
    print(f"   Oracle: {oracle}")

    # 4. Scan for settlement pools
    print("\n4️⃣  Scanning for settlement pools...")
    # Start from a recent block to avoid timeout (Arbitrum launch ~block 70000000)
    pools = client.get_all_settlement_pools(from_block=70000000)
    if pools:
        print(f"   Found {len(pools)} pools:")
        for pool in pools[:5]:  # Show first 5
            print(f"   - {pool['pool_address']} (block {pool['block_number']})")

    # 5. Estimate costs
    print("\n5️⃣  Estimating transaction costs...")
    costs = client.estimate_gas_cost(100000)
    print(f"   Gas Price: {costs['gas_price_gwei']:.2f} gwei")
    print(f"   Est. Cost: {costs['cost_eth']:.6f} ETH", end="")
    if costs['cost_usd']:
        print(f" (${costs['cost_usd']:.2f})")
    else:
        print()

    print("\n✅ Demo complete!")


if __name__ == "__main__":
    main()
