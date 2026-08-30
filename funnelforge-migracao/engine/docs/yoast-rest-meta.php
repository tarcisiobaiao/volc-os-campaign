<?php
/**
 * Expose Yoast SEO postmeta to the WordPress REST API for the funnel post types.
 *
 * WHY: funnel-forge writes the Yoast SEO title / meta description / focus
 * keyword via the REST API (WordPressPublisher.set_yoast ->
 * POST /wp-json/wp/v2/<type>/<id> with { meta: { _yoast_wpseo_* } }).
 * By default those meta keys are NOT registered with `show_in_rest`, so
 * WordPress accepts the request (HTTP 200) but SILENTLY discards them and
 * nothing is stored. This snippet registers them so the writes persist.
 *
 * INSTALL (pick one):
 *   - Best: drop this file in wp-content/mu-plugins/ (loads automatically), or
 *   - paste the body of the `init` callback into a "Code Snippets" plugin, or
 *   - append it to your (child) theme's functions.php.
 *
 * Adjust the $post_types list if your funnel uses different slugs
 * (defaults: `rec` for interior posts, `r` for the Elementor landing page).
 */

add_action('init', function () {
    $post_types = ['rec', 'r'];
    $keys = ['_yoast_wpseo_title', '_yoast_wpseo_metadesc', '_yoast_wpseo_focuskw'];

    foreach ($post_types as $post_type) {
        foreach ($keys as $key) {
            register_post_meta($post_type, $key, [
                'show_in_rest'  => true,
                'single'        => true,
                'type'          => 'string',
                'auth_callback' => function () {
                    return current_user_can('edit_posts');
                },
            ]);
        }
    }
});
