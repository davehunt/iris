# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.


from iris.test_case import *


class Test(BaseTest):

    def __init__(self, app):
        BaseTest.__init__(self, app)
        self.meta = 'Websites can be bookmarked via URL drag & drop onto the Bookmarks Sidebar.'

    def run(self):

        url = 'bing.com'
        draggable_url = 'draggable_url_bing.png'
        sidebar_bookmarks = 'library_bookmarks.png'
        drag_area = 'drag_area_bing.png'
        bing_home = 'bing_home.png'
        bing_bookmark = 'bing_bookmark.png'
        bookmarked_star = 'blue_star.png'

        navigate(url)

        expected = exists(bing_home, 10)
        assert_true(self, expected, 'Bing has been successfully accessed.')

        bookmarks_sidebar('open')

        try:
            wait(sidebar_bookmarks, 10)
            logger.debug('Bookmarks section can be accessed.')
            click(sidebar_bookmarks)
        except FindError:
            raise FindError('Bookmarks section is not present on the page, aborting.')

        select_location_bar()

        dragDrop(draggable_url, drag_area, 0.5)

        star_shaped_button_assert = exists(bookmarked_star, 10)
        assert_true(self, star_shaped_button_assert, 'Star-shaped button has changed its color to blue.')

        bookmarked_url_assert = exists(bing_bookmark, 10)
        assert_true(self, bookmarked_url_assert, 'Bing page has been successfully bookmarked via URL onto the '
                                                 'Bookmarks Sidebar')
