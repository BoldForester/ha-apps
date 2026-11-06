// OpenWebRX+ receiver plugins (installed by the Home Assistant app wrapper).
// More plugins: https://0xaf.github.io/openwebrxplus-plugins/
const rp_url = 'https://0xaf.github.io/openwebrxplus-plugins/receiver';

Plugins.load(rp_url + '/utils/utils.js').then(async function () {
	await Plugins.load(rp_url + '/notify/notify.js');
	// Frequency scanner: Scan / Skip / Block panel in the receiver controls.
	Plugins.load(rp_url + '/freq_scanner/freq_scanner.js');
	if (typeof MapPlugin !== 'undefined') MapPlugin.init();
	if (typeof SunPlugin !== 'undefined') SunPlugin.init();
});
