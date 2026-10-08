from datetime import datetime
import unittest
from unittest.mock import patch
import service
import birdweather

class TodayTest(unittest.TestCase):
 def test_ny_midnight_and_dst(self):
  for instant,day,end in [('2026-10-08T03:59:59+00:00','2026-10-07','2026-10-08'),('2026-10-08T04:00:00+00:00','2026-10-08','2026-10-09'),('2026-03-08T16:00:00+00:00','2026-03-08','2026-03-09'),('2026-11-01T16:00:00+00:00','2026-11-01','2026-11-02')]:
   self.assertEqual(service.today_period(datetime.fromisoformat(instant)),{'from':day,'to':end,'timezone':'America/New_York'})
 def test_period_reaches_station_query_and_empty_is_valid(self):
  period=service.today_period()
  with patch.object(birdweather,'_graphql',return_value={'data':{'station':{'id':'19176'},'topSpecies':[]}}) as query:
   self.assertEqual(birdweather.species_for_station('19176',drawable=[],period=period),[])
   self.assertEqual(query.call_args.kwargs['variables']['period'],period)
 def test_empty_day_has_valid_image(self):
  image=service.empty_today_image({'title':'Avian Visitors','subtitle':'Heard Today'})
  self.assertEqual(image.size,(1200,1600));self.assertEqual(image.getpixel((0,0)),(255,255,255))
