/* Initialise Select2 tag mode on all ArrayWidget inputs once DOM is ready.
 * select2.full.js is loaded before jquery.init.js in ArrayWidget.Media so
 * that Select2 can register .select2() on window.jQuery while it still
 * exists; jquery.init.js then runs noConflict(true) but django.jQuery is
 * the same object, so .select2() remains available here.
 */
django.jQuery(function ($) {
	$('.array-field-input').select2({
		tags: true,
		tokenSeparators: [','],
		width: '100%',
	});
});
