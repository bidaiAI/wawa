'use client'

import { getDefaultConfig } from '@rainbow-me/rainbowkit'
import { fallback, http } from 'viem'
import { base, bsc } from 'wagmi/chains'

/**
 * Wagmi + RainbowKit configuration for wallet connection.
 *
 * Supports Base (USDC) and BSC (USDT).
 * WalletConnect projectId is optional — MetaMask injected works without it.
 */

export const config = getDefaultConfig({
  appName: 'Mortal AI',
  // WalletConnect projectId — get one at https://cloud.walletconnect.com
  // Optional: MetaMask injected connector works without it
  projectId: process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID || 'mortal-ai-demo',
  chains: [base, bsc],
  transports: {
    [base.id]: fallback([
      http(process.env.NEXT_PUBLIC_BASE_RPC_URL || 'https://mainnet.base.org'),
      http('https://base-rpc.publicnode.com'),
    ]),
    [bsc.id]: fallback([
      http(process.env.NEXT_PUBLIC_BSC_RPC_URL || 'https://bsc-dataseed.bnbchain.org'),
      http('https://bsc-rpc.publicnode.com'),
    ]),
  },
  ssr: true,
})

// Token addresses per chain
export const TOKENS: Record<number, { address: `0x${string}`; symbol: string; decimals: number }> = {
  [base.id]: {
    address: '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
    symbol: 'USDC',
    decimals: 6,
  },
  [bsc.id]: {
    address: '0x55d398326f99059fF775485246999027B3197955',
    symbol: 'USDT',
    decimals: 18,
  },
}

// Factory contract addresses — deployed at same address on Base and BSC
// Can be overridden via env vars for development/testing
export const FACTORY_ADDRESSES: Record<number, `0x${string}`> = {
  [base.id]: (process.env.NEXT_PUBLIC_BASE_FACTORY_ADDRESS || '0x50e752b4Fd53d1F6D1b4e54d4e81A365ae52C3FF') as `0x${string}`,
  [bsc.id]: (process.env.NEXT_PUBLIC_BSC_FACTORY_ADDRESS || '0x50e752b4Fd53d1F6D1b4e54d4e81A365ae52C3FF') as `0x${string}`,
}
