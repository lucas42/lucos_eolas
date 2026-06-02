/*
 * array-field-widget.js
 *
 * Django 5.x jquery.init.js uses jQuery.noConflict(true), which removes
 * window.jQuery entirely.  select2.full.js (loaded after this file) falls
 * through to its `factory(jQuery)` fallback and throws "jQuery not found".
 *
 * Fix: synchronously expose django.jQuery as window.jQuery before select2
 * loads so it can register .select2() on it.  Because django.jQuery IS that
 * same jQuery object, .select2() is then available on django.jQuery too.
 */
window.jQuery = window.jQuery || django.jQuery;

/* Initialise Select2 tag mode on all ArrayWidget inputs once DOM is ready. */
django.jQuery(function ($) {
	$('.array-field-input').select2({
		tags: true,
		tokenSeparators: [','],
		width: '100%',
	});
});
