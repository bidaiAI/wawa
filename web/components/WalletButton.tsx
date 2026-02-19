'use client'

import { ConnectButton } from '@rainbow-me/rainbowkit'

/**
 * Reusable wallet connect button styled for the mortal AI theme.
 * Uses RainbowKit's ConnectButton with custom rendering.
 */
export default function WalletButton({ className = '' }: { className?: string }) {
  return (
    <ConnectButton.Custom>
      {({ account, chain, openAccountModal, openChainModal, openConnectModal, mounted }) => {
        const ready = mounted
        const connected = ready && account && chain

        return (
          <div
            className={className}
            {...(!ready && {
              'aria-hidden': true,
              style: { opacity: 0, pointerEvents: 'none', userSelect: 'none' },
            })}
          >
            {(() => {
              if (!connected) {
                return (
                  <button
                    onClick={openConnectModal}
                    className="px-4 py-2 bg-[#00ff88] text-[#0a0a0a] font-bold text-sm rounded-lg
                               hover:bg-[#00cc6a] transition-colors"
                  >
                    Connect Wallet
                  </button>
                )
              }

              if (chain.unsupported) {
                return (
                  <button
                    onClick={openChainModal}
                    className="px-4 py-2 bg-[#ff3b3b] text-white font-bold text-sm rounded-lg
                               hover:bg-[#cc2f2f] transition-colors"
                  >
                    Wrong Network
                  </button>
                )
              }

              return (
                <div className="flex items-center gap-2">
                  <button
                    onClick={openChainModal}
                    className="px-3 py-1.5 bg-[#111111] border border-[#1f2937] rounded-lg
                               text-xs text-[#d1d5db] hover:border-[#00ff8844] transition-colors
                               flex items-center gap-1.5"
                  >
                    {chain.hasIcon && chain.iconUrl && (
                      <img
                        alt={chain.name ?? 'Chain'}
                        src={chain.iconUrl}
                        className="w-4 h-4 rounded-full"
                      />
                    )}
                    {chain.name}
                  </button>

                  <button
                    onClick={openAccountModal}
                    className="px-3 py-1.5 bg-[#111111] border border-[#1f2937] rounded-lg
                               text-xs text-[#00ff88] hover:border-[#00ff8844] transition-colors
                               font-mono"
                  >
                    {account.displayName}
                  </button>
                </div>
              )
            })()}
          </div>
        )
      }}
    </ConnectButton.Custom>
  )
}
