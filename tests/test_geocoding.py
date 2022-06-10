from unittest import TestCase

import dcgeotools as dcg

class GeocodeSingle(TestCase):
    def test_geocode(self):
        s = dcg.geocode("950 25th ST NW", apikey="0254f7c7-b358-4b91-b858-c8785a27b363")
        s = [s["lat"][0], s["lon"][0], s["type"][0]]
        self.assertTrue(s == [38.90209464, -77.05356709, "RESIDENTIAL"])

class GeocodeBatch(TestCase):
    def test_batch(self):
        addresses = ["950 25th ST NW", "ALABAMA AVE SE AND WHEELER RD SE"]
        s = dcg.geocode(addresses, apikey="0254f7c7-b358-4b91-b858-c8785a27b363")
        s = [s["lat"][0], s["lon"][0], s["type"][0], s["lat"][1], s["lon"][1], s["type"][1]]
        self.assertTrue(s == [38.90209464, -77.05356709, "RESIDENTIAL", 38.843688022974, -76.994225590372, "INTERSECTION"])

class GetIntersection(TestCase):
    def test_intersection(self):
        s = dcg.get_intersection(dcg.address_to_MAR("950 25th ST NW"), apikey="0254f7c7-b358-4b91-b858-c8785a27b363")
        self.assertTrue(s == "26TH STREET NW AND I STREET NW")