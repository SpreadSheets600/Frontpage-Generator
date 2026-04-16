import unittest

from main import app


class FlaskRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()

    def test_root_route_serves_html(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)

    def test_feedback_route_serves_html(self):
        response = self.client.get("/feedback/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)

    def test_index_page_download_serves_pdf(self):
        response = self.client.get("/downloads/index-page")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/pdf", response.content_type)


if __name__ == "__main__":
    unittest.main()
