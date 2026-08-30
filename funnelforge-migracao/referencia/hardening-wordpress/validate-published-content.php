<?php
// Run with: wp eval-file /tmp/validate-published-content.php --path=/var/www/creditoup.com.br --allow-root

function volc_collect_html_blocks( $blocks, &$html_blocks ) {
	foreach ( $blocks as $block ) {
		if ( 'core/html' === ( $block['blockName'] ?? '' ) ) {
			$html_blocks[] = $block['innerHTML'];
		}
		if ( ! empty( $block['innerBlocks'] ) ) {
			volc_collect_html_blocks( $block['innerBlocks'], $html_blocks );
		}
	}
}

$posts = get_posts(
	array(
		'post_type'      => 'rec',
		'post_status'    => 'publish',
		'posts_per_page' => -1,
		'orderby'        => 'ID',
		'order'          => 'ASC',
	)
);

$report = array();
$all_ok = true;
$html_block_count = 0;

foreach ( $posts as $post ) {
	$GLOBALS['post'] = $post;
	setup_postdata( $post );
	$html_blocks = array();
	volc_collect_html_blocks( parse_blocks( $post->post_content ), $html_blocks );
	$html_block_count += count( $html_blocks );
	$output = apply_filters( 'the_content', $post->post_content );

	$missing_blocks = array();
	$missing_ids    = array();
	foreach ( $html_blocks as $index => $html ) {
		if ( false === strpos( $output, $html ) ) {
			$missing_blocks[] = $index;
		}

		preg_match_all( '/\bid\s*=\s*(["\'])(.*?)\1/is', $html, $matches );
		foreach ( $matches[2] as $id ) {
			if ( false === strpos( $output, 'id=' . $matches[1][0] . $id . $matches[1][0] ) && ! preg_match( '/\bid\s*=\s*(["\'])' . preg_quote( $id, '/' ) . '\1/i', $output ) ) {
				$missing_ids[] = $id;
			}
		}
	}

	$ok     = ! $missing_blocks && ! $missing_ids;
	$all_ok = $all_ok && $ok;
	$report[] = array(
		'ID'                  => $post->ID,
		'slug'                => $post->post_name,
		'html_blocks'         => count( $html_blocks ),
		'missing_block_index' => $missing_blocks,
		'missing_ids'         => array_values( array_unique( $missing_ids ) ),
		'ok'                  => $ok,
	);
}

wp_reset_postdata();

echo wp_json_encode(
	array(
		'ok'                         => $all_ok,
		'unsafe_lt_p_img_registered' => false !== has_filter( 'the_content', 'lt_p_img' ),
		'post_count'                 => count( $report ),
		'html_block_count'           => $html_block_count,
		'failed_posts'               => array_values(
			array_filter(
				$report,
				static function ( $post_report ) {
					return ! $post_report['ok'];
				}
			)
		),
	),
	JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES
);
