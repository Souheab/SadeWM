import os
import sys
import unittest
from unittest import mock


_src = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_src))

from services.bar import notification_service  # noqa: E402


class TestNotificationService(unittest.TestCase):
    def make_service(self):
        with mock.patch.object(
            notification_service.NotificationService, "_start_server"
        ):
            return notification_service.NotificationService()

    def add_notification(self, service, summary):
        return service._add_notification(
            "tests", summary, "body", "", 5000
        )

    def popup_ids(self, service):
        model = service.popupModel
        return [
            model.data(model.index(row, 0), model.NotificationRole)["id"]
            for row in range(model.rowCount())
        ]

    def test_popup_rows_keep_identity_when_removed_out_of_order(self):
        service = self.make_service()
        ids = [self.add_notification(service, f"notification {i}") for i in range(6)]

        self.assertEqual(self.popup_ids(service), list(reversed(ids)))

        service.removeFromQueueById(ids[2])
        service.removeFromQueueById(ids[5])

        self.assertEqual(
            self.popup_ids(service),
            [ids[4], ids[3], ids[1], ids[0]],
        )
        self.assertEqual(
            [entry["id"] for entry in service.popupQueue],
            [ids[4], ids[3], ids[1], ids[0]],
        )

    def test_dismiss_all_clears_popup_model(self):
        service = self.make_service()
        self.add_notification(service, "one")
        self.add_notification(service, "two")

        service.dismissAll()

        self.assertEqual(service.popupModel.rowCount(), 0)
        self.assertEqual(service.popupQueue, [])
        self.assertEqual(service.notifications, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
