import type { Config } from "tailwindcss";

export default {
	darkMode: ["class"],
	content: [
		"./pages/**/*.{ts,tsx}",
		"./components/**/*.{ts,tsx}",
		"./app/**/*.{ts,tsx}",
		"./src/**/*.{ts,tsx}",
	],
	prefix: "",
	theme: {
		container: {
			center: true,
			padding: '2rem',
			screens: {
				'2xl': '1400px'
			}
		},
		extend: {
			fontFamily: {
				sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
				display: ['Space Grotesk', 'ui-sans-serif', 'system-ui', 'sans-serif'],
			},
			colors: {
				border: 'hsl(var(--border))',
				input: 'hsl(var(--input))',
				'switch-off': 'hsl(var(--switch-off))',
				ring: 'hsl(var(--ring))',
				background: 'hsl(var(--background))',
				foreground: 'hsl(var(--foreground))',
				primary: {
					DEFAULT: 'hsl(var(--primary))',
					foreground: 'hsl(var(--primary-foreground))',
					glow: 'hsl(var(--primary-glow))'
				},
				secondary: {
					DEFAULT: 'hsl(var(--secondary))',
					foreground: 'hsl(var(--secondary-foreground))'
				},
				destructive: {
					DEFAULT: 'hsl(var(--destructive))',
					foreground: 'hsl(var(--destructive-foreground))'
				},
				muted: {
					DEFAULT: 'hsl(var(--muted))',
					foreground: 'hsl(var(--muted-foreground))'
				},
				accent: {
					DEFAULT: 'hsl(var(--accent))',
					foreground: 'hsl(var(--accent-foreground))'
				},
				popover: {
					DEFAULT: 'hsl(var(--popover))',
					foreground: 'hsl(var(--popover-foreground))'
				},
				card: {
					DEFAULT: 'hsl(var(--card))',
					foreground: 'hsl(var(--card-foreground))'
				},
				/* `verified` = a fonte foi OBSERVADA ou reconciliada. Não é sucesso.
				   Separado de `success` de propósito: "eu vi na conta" e "está
				   saudável" levam a decisões diferentes, e o produto vinha
				   pintando as duas com a mesma tinta. */
				verified: {
					DEFAULT: 'hsl(var(--verified))',
					foreground: 'hsl(var(--verified-foreground))'
				},
				success: {
					DEFAULT: 'hsl(var(--success))',
					foreground: 'hsl(var(--success-foreground))'
				},
				warning: {
					DEFAULT: 'hsl(var(--warning))',
					foreground: 'hsl(var(--warning-foreground))'
				},
				info: {
					DEFAULT: 'hsl(var(--info))',
					foreground: 'hsl(var(--info-foreground))'
				},
				sidebar: {
					DEFAULT: 'hsl(var(--sidebar-background))',
					foreground: 'hsl(var(--sidebar-foreground))',
					primary: 'hsl(var(--sidebar-primary))',
					'primary-foreground': 'hsl(var(--sidebar-primary-foreground))',
					accent: 'hsl(var(--sidebar-accent))',
					'accent-foreground': 'hsl(var(--sidebar-accent-foreground))',
					border: 'hsl(var(--sidebar-border))',
					ring: 'hsl(var(--sidebar-ring))'
				}
			},
			borderRadius: {
				lg: 'var(--radius)',
				md: 'calc(var(--radius) - 2px)',
				sm: 'calc(var(--radius) - 4px)'
			},
			/* Um vocabulário de transição para o produto inteiro.
			   O `design.md` manda NOMEAR a propriedade e bane `transition-all`
			   sem exceção. `transition-volc` cobre exatamente o que o contrato
			   autoriza animar — cor, borda, sombra, transform e opacidade — e
			   deixa de fora width, height, top e left, que são layout. */
			transitionProperty: {
				volc: 'color, background-color, border-color, text-decoration-color, fill, stroke, box-shadow, transform, opacity',
			},
			keyframes: {
				'accordion-down': {
					from: {
						height: '0'
					},
					to: {
						height: 'var(--radix-accordion-content-height)'
					}
				},
				'accordion-up': {
					from: {
						height: 'var(--radix-accordion-content-height)'
					},
					to: {
						height: '0'
					}
				},
				'fade-in': {
					'0%': {
						opacity: '0',
						transform: 'translateY(10px)'
					},
					'100%': {
						opacity: '1',
						transform: 'translateY(0)'
					}
				},
				'scale-in': {
					'0%': {
						transform: 'scale(0.95)',
						opacity: '0'
					},
					'100%': {
						transform: 'scale(1)',
						opacity: '1'
					}
				},
				'progress-indeterminate': {
						'0%': { transform: 'translateX(-100%)' },
						'100%': { transform: 'translateX(320%)' }
					},
					'chart-bar': {
					'0%': {
						transform: 'scaleY(0)'
					},
					'100%': {
						transform: 'scaleY(1)'
					}
				}
			},
			animation: {
				'accordion-down': 'accordion-down 0.2s ease-out',
				'accordion-up': 'accordion-up 0.2s ease-out',
				'fade-in': 'fade-in 0.5s ease-out',
				'scale-in': 'scale-in 0.3s ease-out',
				'chart-bar': 'chart-bar 0.8s ease-out',
					'progress-indeterminate': 'progress-indeterminate 1.3s ease-in-out infinite'
			},
			backgroundImage: {
				'gradient-aurora-action': 'var(--gradient-aurora-action)',
				'gradient-dashboard': 'var(--gradient-dashboard)',
				'gradient-primary': 'var(--gradient-primary)',
				'gradient-card': 'var(--gradient-card)',
				'gradient-aurora': 'var(--gradient-aurora)'
			},
			boxShadow: {
				'dashboard': 'var(--shadow-dashboard)',
				'card': 'var(--shadow-card)',
				'elevated': 'var(--shadow-elevated)',
				'glow': 'var(--shadow-glow)'
			}
		}
	},
	plugins: [require("tailwindcss-animate")],
} satisfies Config;