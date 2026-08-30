<?php
/**
 * Plugin Name: VOLC Funnel Hardening
 * Description: Preserva blocos HTML brutos e normaliza botões nos conteúdos do funil (post type rec).
 * Version: 1.0.1
 * Author: VOLC
 */

defined( 'ABSPATH' ) || exit;

final class Volc_Funnel_Hardening {
	private const POST_TYPE = 'rec';

	/** @var array<string,string> */
	private static $raw_html = array();

	public static function boot() {
		add_action( 'after_setup_theme', array( __CLASS__, 'replace_unsafe_theme_filter' ), 1000 );
		add_action( 'init', array( __CLASS__, 'unregister_outline_style' ), 100 );
		add_action( 'enqueue_block_editor_assets', array( __CLASS__, 'unregister_outline_style_in_editor' ) );
		add_action( 'wp_enqueue_scripts', array( __CLASS__, 'enqueue_styles' ) );

		add_filter( 'render_block_data', array( __CLASS__, 'normalize_legacy_outline_attributes' ), 1, 3 );
		add_filter( 'render_block_core/html', array( __CLASS__, 'shield_raw_html' ), 10, 2 );
		add_filter( 'render_block_core/button', array( __CLASS__, 'normalize_legacy_outline_button' ), 10, 2 );
		add_filter( 'the_content', array( __CLASS__, 'restore_raw_html' ), PHP_INT_MAX );
	}

	public static function replace_unsafe_theme_filter() {
		/*
		 * wgc3/functions/images.php registers lt_p_img() at priority 10. Its
		 * optional image group also matches every empty <p>, including markup
		 * inside scripts/templates. Keep the intended image-only unwrap, but
		 * require an actual image in the paragraph.
		 */
		remove_filter( 'the_content', 'lt_p_img', 10 );
		add_filter( 'the_content', array( __CLASS__, 'unwrap_image_only_paragraphs' ), 10 );

		/* wgc3 declares editor-font-sizes without the required preset array. */
		remove_theme_support( 'editor-font-sizes' );
	}

	public static function unwrap_image_only_paragraphs( $content ) {
		$pattern = '~<p\b[^>]*>\s*((?:<a\b[^>]*>\s*)?<img\b[^>]*>(?:\s*</a>)?)\s*</p>~is';
		$result  = preg_replace( $pattern, '$1', $content );

		return null === $result ? $content : $result;
	}

	public static function unregister_outline_style() {
		if ( function_exists( 'unregister_block_style' ) ) {
			unregister_block_style( 'core/button', 'outline' );
		}
	}

	public static function unregister_outline_style_in_editor() {
		$screen = function_exists( 'get_current_screen' ) ? get_current_screen() : null;
		if ( ! $screen || self::POST_TYPE !== $screen->post_type ) {
			return;
		}

		$script = "wp.domReady(function () { wp.blocks.unregisterBlockStyle('core/button', 'outline'); });";
		wp_add_inline_script( 'wp-blocks', $script, 'after' );
	}

	public static function enqueue_styles() {
		if ( ! is_singular( self::POST_TYPE ) ) {
			return;
		}

		$path = __DIR__ . '/volc-funnel-hardening.css';
		wp_enqueue_style(
			'volc-funnel-hardening',
			content_url( 'mu-plugins/volc-funnel-hardening.css' ),
			array(),
			is_readable( $path ) ? (string) filemtime( $path ) : '1.0.0'
		);
	}

	private static function is_rec_content_filter() {
		if ( ! doing_filter( 'the_content' ) ) {
			return false;
		}

		$post_id = get_the_ID();
		return $post_id && self::POST_TYPE === get_post_type( $post_id );
	}

	public static function shield_raw_html( $block_content, $block ) {
		if ( ! self::is_rec_content_filter() ) {
			return $block_content;
		}

		$token = '<!-- VOLC_RAW_HTML_' . hash( 'sha256', $block_content . '|' . count( self::$raw_html ) . '|' . wp_rand() ) . ' -->';
		self::$raw_html[ $token ] = $block_content;

		return $token;
	}

	public static function normalize_legacy_outline_attributes( $parsed_block, $source_block, $parent_block ) {
		if (
			! self::is_rec_content_filter()
			|| 'core/button' !== ( $parsed_block['blockName'] ?? '' )
			|| empty( $parsed_block['attrs']['className'] )
		) {
			return $parsed_block;
		}

		$classes = preg_split( '/\s+/', trim( $parsed_block['attrs']['className'] ) );
		$classes = array_values( array_diff( $classes, array( 'is-style-outline' ) ) );

		if ( $classes ) {
			$parsed_block['attrs']['className'] = implode( ' ', $classes );
		} else {
			unset( $parsed_block['attrs']['className'] );
		}

		return $parsed_block;
	}

	public static function restore_raw_html( $content ) {
		if ( ! self::$raw_html ) {
			return $content;
		}

		$found = array();
		foreach ( self::$raw_html as $token => $html ) {
			if ( false !== strpos( $content, $token ) ) {
				$found[ $token ] = $html;
				unset( self::$raw_html[ $token ] );
			}
		}

		if ( $found ) {
			$content = strtr( $content, $found );
		}

		return $content;
	}

	public static function normalize_legacy_outline_button( $block_content, $block ) {
		if ( ! self::is_rec_content_filter() || false === strpos( $block_content, 'is-style-outline' ) ) {
			return $block_content;
		}

		if ( class_exists( 'WP_HTML_Tag_Processor' ) ) {
			$processor = new WP_HTML_Tag_Processor( $block_content );
			while ( $processor->next_tag() ) {
				if ( $processor->has_class( 'is-style-outline' ) ) {
					$processor->remove_class( 'is-style-outline' );
				}
			}

			return $processor->get_updated_html();
		}

		return preg_replace_callback(
			'/\bclass=(["\'])(.*?)\1/is',
			static function ( $match ) {
				$classes = preg_split( '/\s+/', trim( $match[2] ) );
				$classes = array_values( array_diff( $classes, array( 'is-style-outline' ) ) );
				return 'class=' . $match[1] . implode( ' ', $classes ) . $match[1];
			},
			$block_content
		);
	}
}

Volc_Funnel_Hardening::boot();
