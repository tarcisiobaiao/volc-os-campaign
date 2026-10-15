<?php
/**
 * Plugin Name: VOLC Editorial Notice Owner
 * Description: Keeps the engine notice unless a global disclosure was actually rendered.
 * Version: 1.1.0
 */

defined( 'ABSPATH' ) || exit;

// Guarda na DECLARACAO: a mesma classe carregada por outro arquivo nao derruba o site.
if ( ! class_exists( 'Volc_Editorial_Notice_Owner', false ) ) {

final class Volc_Editorial_Notice_Owner {

	public static function boot() {
		add_filter( 'elementor/element/is_dynamic_content', array( __CLASS__, 'notice_is_dynamic' ), 20, 2 );
		add_filter( 'elementor/frontend/container/should_render', array( __CLASS__, 'container_should_render' ), 20, 2 );
		add_filter( 'the_content', array( __CLASS__, 'remove_prefix' ), 8 );
		add_filter( 'render_block_core/html', array( __CLASS__, 'remove_prefix' ), 5 );
		// 1.1.0: o aviso global saiu do topo para o wp_footer, e o sinal so dispara
		// depois de ele ser impresso, ou seja, DEPOIS do conteudo. A decisao sobre
		// o aviso duplicado passa a acontecer no fim da resposta, quando o sinal ja
		// diz a verdade. Buffer aberto antes do buffer de seguranca do hardening
		// (prioridade 0 < PHP_INT_MAX): o callback deste roda por ultimo e ve o
		// aviso que a rede de seguranca injetou.
		add_action( 'template_redirect', array( __CLASS__, 'start_buffer' ), 0 );
	}

	private static $buffering = false;

	private static function is_public_html_request() {
		if ( is_admin() || wp_doing_ajax() || ( function_exists( 'wp_is_json_request' ) && wp_is_json_request() ) ) {
			return false;
		}
		if ( defined( 'REST_REQUEST' ) && REST_REQUEST ) {
			return false;
		}
		return ! ( is_feed() || is_robots() || is_trackback() || is_embed() );
	}

	public static function start_buffer() {
		if ( self::$buffering || ! self::is_public_html_request() ) {
			return;
		}
		self::$buffering = ob_start( array( __CLASS__, 'remove_engine_notices' ) );
	}

	/**
	 * Fim da resposta: se o aviso global foi efetivamente impresso (sinal), cada
	 * aside CANONICO do motor sai do HTML; qualquer outro aside, ou um aviso do
	 * motor editado, fica. Sem o sinal, nada muda: o aviso do motor e o unico.
	 */
	public static function remove_engine_notices( $html ) {
		if ( ! is_string( $html ) || false === strpos( $html, 'volc-editorial-notice' )
			|| ! did_action( 'volc_editorial_disclosure_rendered' ) ) {
			return $html;
		}
		return preg_replace_callback(
			'#<aside\b[^>]*\bid=(["\'])volc-editorial-notice\1[^>]*>.*?</aside>#is',
			function ( $m ) {
				return self::is_engine_notice( $m[0] ) ? '' : $m[0];
			},
			$html
		);
	}

	private static function global_is_present() {
		return ! is_admin() && ! wp_doing_ajax() && did_action( 'volc_editorial_disclosure_rendered' );
	}

	public static function is_engine_notice( $html ) {
		if ( ! is_string( $html ) || false === strpos( $html, 'volc-editorial-notice' ) || ! class_exists( 'DOMDocument' ) ) {
			return false;
		}
		$doc = new DOMDocument();
		$previous = libxml_use_internal_errors( true );
		$loaded = $doc->loadHTML( '<?xml encoding="UTF-8"><html><body>' . $html . '</body></html>', LIBXML_NONET );
		libxml_clear_errors();
		libxml_use_internal_errors( $previous );
		if ( ! $loaded ) {
			return false;
		}
		$body = $doc->getElementsByTagName( 'body' )->item( 0 );
		$nodes = array();
		foreach ( $body->childNodes as $node ) {
			if ( XML_TEXT_NODE === $node->nodeType && '' === trim( $node->textContent ) ) {
				continue;
			}
			$nodes[] = $node;
		}
		if ( 1 !== count( $nodes ) || ! ( $nodes[0] instanceof DOMElement ) || 'aside' !== $nodes[0]->tagName ) {
			return false;
		}
		$aside = $nodes[0];
		if ( 'volc-editorial-notice' !== $aside->getAttribute( 'id' ) || 'Identidade editorial' !== $aside->getAttribute( 'aria-label' ) ) {
			return false;
		}
		// Match the canonical engine notice, never an arbitrary aside or user copy.
		$strong = $aside->getElementsByTagName( 'strong' );
		if ( 1 !== $strong->length || $strong->item( 0 )->parentNode !== $aside ) {
			return false;
		}
		$aside->removeChild( $strong->item( 0 ) );
		foreach ( $aside->getElementsByTagName( '*' ) as $child ) {
			if ( 'br' !== $child->tagName ) {
				return false;
			}
		}
		$expected = 'Conteúdo editorial independente. Não somos banco, correspondente bancário, órgão público ou plataforma de solicitação. Publicamos guias informativos, sem vínculo com as instituições citadas. Não realizamos contratações nem pedimos senhas, CPF ou dados bancários nesta página.';
		return $expected === trim( preg_replace( '/\s+/u', ' ', $aside->textContent ) );
	}

	public static function container_should_render( $should_render, $element ) {
		if ( ! $should_render || ! self::global_is_present() ) {
			return $should_render;
		}
		return self::notice_container( $element->get_data() ) ? false : $should_render;
	}

	public static function notice_is_dynamic( $dynamic, $data ) {
		// The global header exists only at render time, never cache its decision.
		return $dynamic || self::notice_container( $data );
	}

	private static function notice_container( $data ) {
		$children = $data['elements'] ?? array();
		return 'container' === ( $data['elType'] ?? '' ) && 1 === count( $children )
			&& 'html' === ( $children[0]['widgetType'] ?? '' )
			&& self::is_engine_notice( $children[0]['settings']['html'] ?? '' );
	}

	public static function remove_prefix( $content ) {
		if ( ! self::global_is_present() ) {
			return $content;
		}
		$trimmed = ltrim( $content );
		if ( 0 !== strpos( $trimmed, '<aside ' ) ) {
			return $content;
		}
		$end = strpos( $trimmed, '</aside>' );
		if ( false !== $end && self::is_engine_notice( substr( $trimmed, 0, $end + 8 ) ) ) {
			return substr( $trimmed, $end + 8 );
		}
		return $content;
	}
}

Volc_Editorial_Notice_Owner::boot();
}
