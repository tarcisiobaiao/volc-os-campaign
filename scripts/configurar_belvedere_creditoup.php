<?php

/**
 * Configura de forma idempotente o tema Belvedere para o CreditUp.
 *
 * Uso no servidor:
 *   wp eval-file /caminho/configurar_belvedere_creditoup.php --allow-root
 *
 * O script e idempotente e nao ativa o tema.
 */

if (!defined('ABSPATH')) {
    fwrite(STDERR, "Execute este arquivo com wp eval-file.\n");
    exit(1);
}

$stylesheet = 'belvedere';
$logo_id = 1473;

if (!wp_get_theme($stylesheet)->exists()) {
    fwrite(STDERR, "Tema {$stylesheet} nao instalado.\n");
    exit(2);
}

if (get_post_type($logo_id) !== 'attachment') {
    fwrite(STDERR, "Logo {$logo_id} nao encontrado.\n");
    exit(3);
}

$mods = get_option("theme_mods_{$stylesheet}", array());
if (!is_array($mods)) {
    $mods = array();
}

$mods = array_merge($mods, array(
    'nav_menu_locations' => array(
        'menu-header' => 5,
        'footer-menu' => 6,
    ),
    'custom_logo' => $logo_id,
    'primary_color' => '#002b5c',
    'secondary_color' => '#004909',
    'header_has_color' => 1,
    'header_color_bg' => '#ffffff',
    'header_color_text' => '#1c0604',
    'cookie_consent' => 1,
    'cookies_page' => 3,
    'cookies_consent_text' => 'Este site usa cookies e medição própria conforme os nossos Termos e a [policypage]. Ao continuar navegando, você declara estar ciente dessas práticas.',
    'cookies_consent_button' => 'Entendi',
    'scripts_high_head' => '',
    'scripts_head' => '',
    'scripts_after_body' => '',
    'scripts_before_body' => '',
    'webs_wrapper' => 0,
    'rewarded_links' => 0,
    'button_cta_stack' => 0,
    'cpt_responda' => 1,
    'cpt_lp' => 1,
    'cpt_dis' => 1,
    'cpt_r' => 0,
    'cpt_rec' => 0,
    'cpt_slim' => 0,
    'postinfo' => 1,
    'authorbox' => 1,
    // O funil nao deve oferecer saidas para redes sociais na LP ou pre-sell.
    'sharebox' => 0,
    'related_posts' => 1,
    'show_modallink' => 0,
    'footer_text' => 'Portal editorial independente.',
    'footer_disclaimer' => 'O Crédito Up publica guias informativos, sem vínculo com as instituições citadas. Não somos banco, correspondente bancário, órgão público ou plataforma de inscrição ou contratação. Não solicitamos CPF, senhas, códigos ou dados bancários.',
    'quiz_footer_text' => 'Crédito Up — VOLC NEGOCIOS DIGITAIS LTDA · CNPJ 42.724.548/0001-24',
    'footer_institutional_logo' => wp_get_attachment_url($logo_id),
    'footer_institutional_url' => home_url('/'),
));

$custom_css = <<<'CSS'
#lincebranding {
    display: none !important;
}

.navbar .custom-logo,
.navbar .custom-logo-link img {
    width: auto !important;
    max-width: 280px !important;
    max-height: 68px !important;
    object-fit: contain;
}

.single .entry-content {
    width: 100%;
    max-width: 800px;
    margin-right: auto;
    margin-left: auto;
}

.wp-block-button,
.wp-block-button__link,
.button-shortcode,
.button-block,
.cta-button {
    box-sizing: border-box;
    width: 100% !important;
    max-width: 100% !important;
    text-align: center !important;
}

blockquote::before,
blockquote::after,
.wp-block-quote::before,
.wp-block-quote::after {
    display: none !important;
    content: none !important;
}

blockquote,
.wp-block-quote {
    margin: 1.5em 0 !important;
    padding: 1em 1.5em !important;
    border-left: 4px solid var(--primary-color, #002b5c);
    background-color: #f9f9f9 !important;
    color: #555 !important;
}

.cookie-consent {
    overflow: hidden;
    border: 1px solid rgba(0, 43, 92, 0.12);
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.98);
    color: #172033;
}

.cookie-consent .btn-accept {
    min-height: 48px;
    font-size: 0.95rem;
    font-weight: 700;
}

/*
 * As LPs do CPT r usam o shell do tema apenas para obter wp_head/wp_footer e
 * o aviso nativo. O conteudo Elementor continua full-screen, sem header,
 * titulo, footer institucional, author box ou relacionados do portal.
 */
.single-r > .site-header,
.single-r > footer.site-footer,
.single-r .entry-header,
.single-r article > hr,
.single-r .author-box,
.single-r .related-posts {
    display: none !important;
}

.single-r main.site-main,
.single-r main.site-main > .container,
.single-r main.site-main > .container > .row,
.single-r main.site-main > .container > .row > [class*="col-"] {
    width: 100% !important;
    max-width: none !important;
    margin: 0 !important;
    padding: 0 !important;
}

.single-r .entry-content {
    width: 100% !important;
    max-width: none !important;
    margin: 0 !important;
}

@media (max-width: 768px) {
    .container-fluid {
        padding-right: 20px !important;
        padding-left: 20px !important;
    }

    .navbar .custom-logo,
    .navbar .custom-logo-link img {
        max-width: 220px !important;
        max-height: 54px !important;
    }

    .cookie-consent {
        width: 100%;
        border-right: 0;
        border-bottom: 0;
        border-left: 0;
        border-radius: 14px 14px 0 0;
    }

    ins.adsbygoogle {
        min-height: 90px;
    }
}

@media (min-width: 769px) {
    ins.adsbygoogle {
        min-height: 120px;
    }
}
CSS;

$css_post = wp_update_custom_css_post($custom_css, array('stylesheet' => $stylesheet));
if (is_wp_error($css_post)) {
    fwrite(STDERR, 'Falha ao salvar CSS: ' . $css_post->get_error_message() . "\n");
    exit(4);
}
$mods['custom_css_post_id'] = (int) $css_post->ID;

update_option("theme_mods_{$stylesheet}", $mods, false);

$grid_widgets = get_option('widget_grid_widget', array());
if (!is_array($grid_widgets)) {
    $grid_widgets = array();
}
$grid_widgets[2] = array(
    'title' => 'Mais conteúdos',
    'category' => '',
    'posts_per_page' => 8,
);
$grid_widgets['_multiwidget'] = 1;
update_option('widget_grid_widget', $grid_widgets, false);

$sidebars = get_option('sidebars_widgets', array());
if (!is_array($sidebars)) {
    $sidebars = array();
}
$sidebars['home_widgets_area'] = array('grid_widget-2');
$sidebars['sidebar'] = array();
update_option('sidebars_widgets', $sidebars, false);

echo wp_json_encode(array(
    'configured' => true,
    'stylesheet' => $stylesheet,
    'custom_logo' => $logo_id,
    'custom_css_post_id' => (int) $css_post->ID,
    'home_widgets' => $sidebars['home_widgets_area'],
    'webs_wrapper' => $mods['webs_wrapper'],
    'cookie_consent' => $mods['cookie_consent'],
    'cpt_owners' => array(
        'theme' => array('responda', 'lp', 'dis'),
        'plugin' => array('r', 'rec'),
    ),
), JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
