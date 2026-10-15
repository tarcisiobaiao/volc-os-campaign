<?php
/**
 * Plugin Name: Credito Up Compliance Hardening
 * Description: Exibe a declaracao editorial e desativa comentarios no site publico.
 * Version: 1.1.0
 * Author: VOLC
 *
 * MU-plugin. Ver INSTALACAO-HARDENING.md antes de instalar: inventario dos
 * arquivos ja existentes no servidor, comparacao de hashes, troca no MESMO nome
 * de arquivo e rollback.
 */

defined( 'ABSPATH' ) || exit;

// A guarda envolve a DECLARACAO da classe, nao so a instanciacao: a mesma classe
// carregada por outro arquivo (copia antiga com outro nome) nao vira
// "Cannot redeclare class", que derrubaria o site inteiro, wp-admin inclusive.
if ( ! class_exists( 'Creditoup_Compliance_Hardening', false ) ) {

	final class Creditoup_Compliance_Hardening {

		const VERSION = '1.1.0';
		const CSS     = 'creditoup-compliance-hardening.css';

		/** @var bool O aviso global ja saiu nesta resposta. */
		private static $rendered = false;

		/** @var bool O buffer de rede de seguranca foi aberto por este plugin. */
		private static $buffering = false;

		public static function boot() {
			// 15/10/2026 (operador): o aviso fica no FIM, perto do rodape, para nao
			// ocupar a primeira dobra. O sinal volc_editorial_disclosure_rendered sai
			// SOMENTE depois de o aviso ser impresso (EDITORIAL-NOTICE.md).
			add_action( 'wp_footer', array( __CLASS__, 'render_editorial_disclosure' ), 1 );
			// Rede de seguranca: template que nao executa wp_footer nao termina sem aviso.
			add_action( 'template_redirect', array( __CLASS__, 'start_fallback_buffer' ), PHP_INT_MAX );
			add_action( 'wp_enqueue_scripts', array( __CLASS__, 'enqueue_styles' ), 1 );
			add_action( 'init', array( __CLASS__, 'disable_comment_support' ), 100 );

			add_filter( 'comments_open', '__return_false', 100 );
			add_filter( 'pings_open', '__return_false', 100 );
			add_filter( 'comments_array', '__return_empty_array', 100 );
		}

		private static function is_public_html_request() {
			if ( is_admin() || wp_doing_ajax() || ( function_exists( 'wp_is_json_request' ) && wp_is_json_request() ) ) {
				return false;
			}
			if ( defined( 'REST_REQUEST' ) && REST_REQUEST ) {
				return false;
			}
			return ! ( is_feed() || is_robots() || is_trackback() || is_embed() );
		}

		public static function disclosure_html() {
			return '<aside class="creditoup-editorial-disclosure" aria-label="Transparência editorial">'
				. '<div class="creditoup-editorial-disclosure__inner">'
				. '<strong>Portal editorial independente.</strong> '
				. '<span>O Crédito Up publica guias informativos, sem vínculo com as instituições citadas. '
				. 'Não somos banco, correspondente bancário, órgão público ou plataforma de inscrição ou contratação. '
				. 'Não solicitamos CPF, senhas, códigos ou dados bancários.</span>'
				. '</div></aside>';
		}

		public static function render_editorial_disclosure() {
			if ( self::$rendered || ! self::is_public_html_request() ) {
				return;
			}
			echo self::disclosure_html(); // phpcs:ignore WordPress.Security.EscapeOutput -- markup fixo.
			self::$rendered = true;
			// Depois do echo, nunca antes: quem ouve o sinal (volc-editorial-notice-owner)
			// pode confiar que o aviso global ja esta na pagina.
			do_action( 'volc_editorial_disclosure_rendered' );
		}

		public static function start_fallback_buffer() {
			if ( self::$buffering || ! self::is_public_html_request() ) {
				return;
			}
			self::$buffering = ob_start( array( __CLASS__, 'ensure_disclosure' ) );
		}

		/**
		 * Callback do buffer: se o template nao executou wp_footer (ou parou antes),
		 * o aviso entra antes do ultimo </body>, ou no fim do documento. So mexe em
		 * HTML; JSON, XML e respostas vazias passam intactos.
		 */
		public static function ensure_disclosure( $html ) {
			if ( self::$rendered || ! is_string( $html ) || '' === trim( $html ) ) {
				return $html;
			}
			foreach ( headers_list() as $header ) {
				if ( 0 === stripos( $header, 'content-type:' ) && false === stripos( $header, 'text/html' ) ) {
					return $html;
				}
			}
			if ( false === stripos( $html, '<html' ) && false === stripos( $html, '<body' ) ) {
				return $html;
			}
			self::$rendered = true;
			$pos = strripos( $html, '</body>' );
			if ( false === $pos ) {
				return $html . self::disclosure_html();
			}
			return substr( $html, 0, $pos ) . self::disclosure_html() . substr( $html, $pos );
		}

		public static function stylesheet_url() {
			$dir = wp_normalize_path( __DIR__ );
			if ( defined( 'WPMU_PLUGIN_DIR' ) && defined( 'WPMU_PLUGIN_URL' )
				&& wp_normalize_path( WPMU_PLUGIN_DIR ) === $dir ) {
				return trailingslashit( WPMU_PLUGIN_URL ) . self::CSS;
			}
			return plugins_url( self::CSS, __FILE__ );
		}

		public static function enqueue_styles() {
			$path = __DIR__ . '/' . self::CSS;
			if ( ! is_readable( $path ) ) {
				return; // Sem o CSS versionado ao lado, nenhum <link> para um 404.
			}
			wp_enqueue_style(
				'creditoup-compliance-hardening',
				self::stylesheet_url(),
				array(),
				self::VERSION . '-' . filemtime( $path )
			);
		}

		public static function disable_comment_support() {
			foreach ( get_post_types() as $post_type ) {
				if ( post_type_supports( $post_type, 'comments' ) ) {
					remove_post_type_support( $post_type, 'comments' );
				}

				if ( post_type_supports( $post_type, 'trackbacks' ) ) {
					remove_post_type_support( $post_type, 'trackbacks' );
				}
			}
		}
	}

	Creditoup_Compliance_Hardening::boot();
}
