<?php
/**
 * Plugin Name: VOLC Editorial Notice Owner
 * Description: Keeps the engine notice unless a global disclosure was actually rendered.
 * Version: 1.0.0
 */

defined( 'ABSPATH' ) || exit;

final class Volc_Editorial_Notice_Owner {

	public static function boot() {
		add_filter( 'elementor/element/is_dynamic_content', array( __CLASS__, 'notice_is_dynamic' ), 20, 2 );
		add_filter( 'elementor/frontend/container/should_render', array( __CLASS__, 'container_should_render' ), 20, 2 );
		add_filter( 'the_content', array( __CLASS__, 'remove_prefix' ), 8 );
		add_filter( 'render_block_core/html', array( __CLASS__, 'remove_prefix' ), 5 );
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
