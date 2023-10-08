"""

Sample bot that wraps GPT-3.5-Turbo but makes responses use all-caps.

"""
from __future__ import annotations

from typing import AsyncIterable
import requests
import io
from io import StringIO
from contextlib import redirect_stdout
import re
import pandas as pd
from fastapi_poe import PoeBot
from fastapi_poe.client import stream_request
from fastapi_poe.types import (
    PartialResponse,
    QueryRequest,
    SettingsRequest,
    SettingsResponse,
)

BASE_BOT = "GPT-3.5-Turbo"
# BASE_BOT = "Code-Llama-34b"

PROMPT_TEMPLATE = """

"""


class EDA_bot(PoeBot):
    def check_attachment(self, request: QueryRequest):
        return len(request.query[-1].attachments) > 0

    async def get_response(
        self, request: QueryRequest
    ) -> AsyncIterable[PartialResponse]:
        if self.check_attachment(request):
            request.query[-1].content

            print("there is an attachment")
            # assume that we just take the first attachment

            attachment_info = request.query[-1].attachments[0]
            attachment_url = attachment_info.url
            response = requests.get(attachment_url)
            if response.status_code == 200:
                # The request was successful, so proceed to read the CSV content
                csv_data = response.text
            else:
                # Handle the case when the request was not successful
                print(f"Failed to download CSV. Status code: {response.status_code}")
                csv_data = None
            if csv_data:
                df = pd.read_csv(io.StringIO(csv_data))
                print(df.head(1))

                #
                async def concat_stream_request(request):
                    output_list = []
                    async for msg in stream_request(
                        request, BASE_BOT, request.access_key
                    ):
                        output_list.append(msg.text)
                    return output_list

                concatenated_msgs = await concat_stream_request(request)
                joined_messages = "".join(concatenated_msgs)
                code_blocks = re.findall(r"```(.*?)```", joined_messages, re.DOTALL)
                print(joined_messages)
                print(code_blocks)
                print(f"{len(code_blocks)=}")
                f = StringIO()
                with redirect_stdout(f):
                    exec(code_blocks[0])
                output_from_code = f.getvalue()

                yield PartialResponse(text=output_from_code)

    async def get_settings(self, setting: SettingsRequest) -> SettingsResponse:
        return SettingsResponse(
            server_bot_dependencies={BASE_BOT: 1},
            allow_attachments=True,
            introduction_message="hi im a pandasai wrapper",
        )
