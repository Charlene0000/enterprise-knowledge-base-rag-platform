import asyncio
import os
import unittest
from unittest.mock import patch

if os.getenv("RUN_FULL_TESTS") != "1":
    raise unittest.SkipTest("set RUN_FULL_TESTS=1 to run legacy full-stack tests")

from fastapi import BackgroundTasks

from web.api import query_service


class QueryServiceTests(unittest.TestCase):
    def test_run_query_graph_non_stream_returns_final_state(self):
        expected_state = {
            "session_id": "session-test",
            "original_query": "如何调节温度",
            "answer": "请按照说明书设置目标温度。",
        }

        with (
            patch.object(query_service, "KBQueryWorkflow") as workflow_class,
            patch.object(query_service, "update_task_status") as update_status,
        ):
            workflow_class.return_value.run.return_value = expected_state

            result = query_service.run_query_graph(
                session_id="session-test",
                user_query="如何调节温度",
                is_stream=False,
            )

        self.assertEqual(result, expected_state)
        workflow_class.return_value.run.assert_called_once_with(
            {
                "original_query": "如何调节温度",
                "session_id": "session-test",
                "is_stream": False,
            },
            stream=False,
        )
        update_status.assert_called_once_with(
            "session-test",
            query_service.TASK_STATUS_COMPLETED,
            False,
        )

    def test_non_stream_query_offloads_workflow_to_thread(self):
        captured = {}

        async def fake_to_thread(function, *args, **kwargs):
            captured["function"] = function
            captured["args"] = args
            captured["kwargs"] = kwargs
            return {"answer": "线程池返回的最终答案"}

        request = query_service.QueryRequest(
            query="如何调节温度",
            session_id="session-test",
            is_stream=False,
        )

        with (
            patch.object(query_service.asyncio, "to_thread", new=fake_to_thread),
            patch.object(query_service, "update_task_status"),
            patch.object(query_service, "get_done_task_list", return_value=["生成答案"]),
        ):
            response = asyncio.run(
                query_service.query(BackgroundTasks(), request)
            )

        self.assertIs(captured["function"], query_service.run_query_graph)
        self.assertEqual(
            captured["args"],
            ("session-test", "如何调节温度", False),
        )
        self.assertEqual(captured["kwargs"], {})
        self.assertEqual(response["answer"], "线程池返回的最终答案")
        self.assertEqual(response["done_list"], ["生成答案"])


if __name__ == "__main__":
    unittest.main()
