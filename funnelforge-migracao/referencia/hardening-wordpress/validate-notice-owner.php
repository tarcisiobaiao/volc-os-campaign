<?php
// Standalone tests. Does not bootstrap WordPress or write to its database.
define( 'ABSPATH', __DIR__ );
$global_rendered = false;
$admin_context = false;
$ajax_context = false;
function add_filter() {}
function is_admin() { return $GLOBALS['admin_context']; }
function wp_doing_ajax() { return $GLOBALS['ajax_context']; }
function did_action( $name ) { return $GLOBALS['global_rendered'] ? 1 : 0; }
require __DIR__ . '/volc-editorial-notice-owner.php';

function check( $ok, $label ) {
	if ( ! $ok ) { throw new RuntimeException( $label ); }
	echo 'PASS ' . $label . PHP_EOL;
}
$notice = '<aside id="volc-editorial-notice" aria-label="Identidade editorial"><strong>creditoup.com.br</strong><br>Conteúdo editorial independente. Não somos banco, correspondente bancário, órgão público ou plataforma de solicitação. Publicamos guias informativos, sem vínculo com as instituições citadas. Não realizamos contratações nem pedimos senhas, CPF ou dados bancários nesta página.</aside>';
$other = '<p>User content unchanged.</p>';
$element = new class( $notice ) {
	public $data;
	public function __construct( $html ) {
		$this->data = array( 'elType' => 'container', 'elements' => array( array( 'widgetType' => 'html', 'settings' => array( 'html' => $html ) ) ) );
	}
	public function get_data() { return $this->data; }
};
check( Volc_Editorial_Notice_Owner::is_engine_notice( $notice ), 'canonical notice recognized' );
check( Volc_Editorial_Notice_Owner::notice_is_dynamic(false, $element->data), 'notice is dynamic even without global' );
check( ! Volc_Editorial_Notice_Owner::notice_is_dynamic(false, array('elType' => 'container')), 'ordinary container stays cacheable' );
check( ! Volc_Editorial_Notice_Owner::is_engine_notice( $notice . $other ), 'extra content preserved' );
check( ! Volc_Editorial_Notice_Owner::is_engine_notice( str_replace( 'Não somos', 'Somos', $notice ) ), 'edited notice preserved' );
check( Volc_Editorial_Notice_Owner::container_should_render( true, $element ), 'fallback without global' );
check( $notice . $other === Volc_Editorial_Notice_Owner::remove_prefix( $notice . $other ), 'article fallback without global' );
$global_rendered = true;
check( ! Volc_Editorial_Notice_Owner::container_should_render( true, $element ), 'duplicate container removed' );
check( $other === Volc_Editorial_Notice_Owner::remove_prefix( $notice . $other ), 'article body preserved byte for byte' );
check( $other . $notice === Volc_Editorial_Notice_Owner::remove_prefix( $other . $notice ), 'non-prefix notice preserved' );
$element->data['elements'][] = array( 'widgetType' => 'heading' );
check( Volc_Editorial_Notice_Owner::container_should_render( true, $element ), 'mixed container preserved' );
$admin_context = true;
check( $notice === Volc_Editorial_Notice_Owner::remove_prefix( $notice ), 'editor preserved' );
$admin_context = false;
$ajax_context = true;
check( $notice === Volc_Editorial_Notice_Owner::remove_prefix( $notice ), 'ajax preserved' );
