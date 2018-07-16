# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


from iris.test_case import *


class Test(BaseTest):

    def __init__(self, app):
        BaseTest.__init__(self, app)
        self.meta = 'This is a test case that checks the zoom level on multiple tabs for multiple sites using the ' \
                    'mouse wheel.'

    def run(self):
        url_1 = LocalWeb.FIREFOX_TEST_SITE
        url_2 = LocalWeb.FOCUS_TEST_SITE
        url_bar_default_zoom_level = 'url_bar_default_zoom_level.png'
        url_bar_110_zoom_level = 'url_bar_110_zoom_level.png'

        navigate(url_1)

        expected = exists(LocalWeb.FIREFOX_LOGO, 10)
        assert_true(self, expected, 'Page successfully loaded, firefox logo found.')

        region = create_region_for_url_bar()

        expected = region.exists(url_bar_default_zoom_level, 10)
        assert_true(self, expected, 'Zoom level not displayed by default in the url bar.')

        # zoom in ONE time.
        zoom_with_mouse_wheel(1, ZoomType.IN)

        new_region = create_region_for_url_bar()

        expected = new_region.exists(url_bar_110_zoom_level, 10)
        assert_true(self, expected, 'Zoom level successfully increased, zoom controls found in the url bar.')

        new_tab()

        navigate(url_1)
        time.sleep(DEFAULT_UI_DELAY)

        expected = new_region.exists(url_bar_110_zoom_level, 10)
        assert_true(self, expected, 'Zoom level still displays 110% in the new tab opened for the site for which the '
                                    'zoom level was set.')

        new_tab()

        navigate(url_2)
        time.sleep(DEFAULT_UI_DELAY)

        expected = exists(LocalWeb.FOCUS_LOGO, 10)
        assert_true(self, expected, 'Page successfully loaded, focus logo found.')

        # Zoom level set for one site does not propagate to other sites.
        expected = not new_region.exists(url_bar_110_zoom_level, 10)
        assert_true(self, expected, 'Zoom level not displayed in the url bar for teh second site.')
