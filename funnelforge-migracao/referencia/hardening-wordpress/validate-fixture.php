<?php
// Run with: wp eval-file /tmp/validate-fixture.php --path=/var/www/creditoup.com.br --allow-root

if ( ! class_exists( 'Volc_Funnel_Hardening' ) ) {
	require_once '/tmp/volc-funnel-hardening.php';
	Volc_Funnel_Hardening::replace_unsafe_theme_filter();
}

global $post;
$post = get_post( 2080 );
setup_postdata( $post );

$fixture = <<<'HTML'
<!-- wp:paragraph --><p id="normal-empty" data-state="idle"></p><!-- /wp:paragraph -->
<!-- wp:html --><p id="raw-empty" data-state="idle"></p><script>const tpl = '<p id="js-empty"></p>';</script><template><p id="template-empty"></p></template><div id="raw-div"></div><!-- /wp:html -->
<!-- wp:image --><figure class="wp-block-image"><p id="image-paragraph"><img src="https://example.com/test.png" alt=""></p></figure><!-- /wp:image -->
<!-- wp:buttons --><div class="wp-block-buttons"><!-- wp:button {"className":"is-style-outline"} --><div class="wp-block-button is-style-outline"><a class="wp-block-button__link wp-element-button">Teste</a></div><!-- /wp:button --></div><!-- /wp:buttons -->
HTML;

$output = apply_filters( 'the_content', $fixture );

$checks = array(
	'unsafe_filter_removed'       => false === has_filter( 'the_content', 'lt_p_img' ),
	'normal_empty_p_preserved'    => false !== strpos( $output, 'id="normal-empty"' ),
	'raw_empty_p_preserved'       => false !== strpos( $output, 'id="raw-empty"' ),
	'js_string_preserved'         => false !== strpos( $output, 'id="js-empty"' ),
	'template_content_preserved'  => false !== strpos( $output, 'id="template-empty"' ),
	'raw_div_preserved'           => false !== strpos( $output, 'id="raw-div"' ),
	'legacy_outline_removed'      => false === strpos( $output, 'is-style-outline' ),
	'image_paragraph_unwrapped'   => false === strpos( $output, 'id="image-paragraph"' ),
	'raw_token_fully_restored'    => false === strpos( $output, 'VOLC_RAW_HTML_' ),
);

echo wp_json_encode(
	array(
		'ok'     => ! in_array( false, $checks, true ),
		'checks' => $checks,
	),
	JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES
);

wp_reset_postdata();
