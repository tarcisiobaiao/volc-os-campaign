<?php
/**
 * Plugin Name: Credito Up Compliance Hardening
 * Description: Exibe a declaracao editorial e desativa comentarios no site publico.
 * Version: 1.0.0
 * Author: VOLC
 */

defined( 'ABSPATH' ) || exit;

final class Creditoup_Compliance_Hardening {
	public static function boot() {
		// 15/10/2026 (operador): o aviso continua em todas as páginas, mas no FIM,
		// perto do rodapé, para não ocupar a primeira dobra. O sinal
		// volc_editorial_disclosure_rendered segue no TOPO (wp_body_open), antes
		// do conteúdo: é ele que faz o volc-editorial-notice-owner retirar o aviso
		// duplicado que o motor põe no corpo das páginas.
		add_action( 'wp_body_open', array( __CLASS__, 'signal_editorial_disclosure' ), 1 );
		add_action( 'wp_footer', array( __CLASS__, 'render_editorial_disclosure' ), 1 );
		add_action( 'wp_enqueue_scripts', array( __CLASS__, 'enqueue_styles' ), 1 );
		add_action( 'init', array( __CLASS__, 'disable_comment_support' ), 100 );

		add_filter( 'comments_open', '__return_false', 100 );
		add_filter( 'pings_open', '__return_false', 100 );
		add_filter( 'comments_array', '__return_empty_array', 100 );
	}

	public static function signal_editorial_disclosure() {
		if ( is_admin() || wp_doing_ajax() ) {
			return;
		}
		do_action( 'volc_editorial_disclosure_rendered' );
	}

	public static function render_editorial_disclosure() {
		if ( is_admin() || wp_doing_ajax() || ! did_action( 'volc_editorial_disclosure_rendered' ) ) {
			return;
		}
		?>
		<aside class="creditoup-editorial-disclosure" aria-label="Transparência editorial">
			<div class="creditoup-editorial-disclosure__inner">
				<strong>Portal editorial independente.</strong>
				<span>O Crédito Up publica guias informativos, sem vínculo com as instituições citadas. Não somos banco, correspondente bancário, órgão público ou plataforma de inscrição ou contratação. Não solicitamos CPF, senhas, códigos ou dados bancários.</span>
			</div>
		</aside>
		<?php
	}

	public static function enqueue_styles() {
		$path = __DIR__ . '/creditoup-compliance-hardening.css';
		wp_enqueue_style(
			'creditoup-compliance-hardening',
			content_url( 'mu-plugins/creditoup-compliance-hardening.css' ),
			array(),
			is_readable( $path ) ? (string) filemtime( $path ) : '1.0.0'
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
