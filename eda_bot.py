"""

Sample bot that wraps GPT-3.5-Turbo but makes responses use all-caps.

"""
from __future__ import annotations
from typing import AsyncIterable
import requests
import io
import base64
from io import StringIO, BytesIO
from contextlib import redirect_stdout
import re
import matplotlib.pyplot as plt
import pandas as pd
from fastapi_poe import PoeBot
from fastapi_poe.client import stream_request
from fastapi_poe.types import (
    PartialResponse,
    QueryRequest,
    SettingsRequest,
    SettingsResponse,
)

BASE_BOT = "data_analyst_bro"
# BASE_BOT = "Code-Llama-34b"


class EDA_bot(PoeBot):
    def check_attachment(self, request: QueryRequest):
        return len(request.query[-1].attachments) > 0

    def apply_template(self, df, query):
        return f"""You are given a pandas dataframe with the variable name df. Follow the query provided and generate the reasoning to answer the question. \
        Finally, generate the correct code that answer the question and save the output to a new variable called output_df. \
        Also, appropriately plot the resulting dataframe using matplotlib. run fig = plt.figure() first before adding the title or axis. do not do plt.show(). \
        You are also provided some details of the dataframe. The columns of the dataframe are {df.columns}.\
        The head of the dataframe are {df.head()} Query: {query}"""

    async def get_response(
        self, request: QueryRequest
    ) -> AsyncIterable[PartialResponse]:
        if self.check_attachment(request):
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

                def upload(fig, client_id="b9123fd27937c4e"):
                    buf = BytesIO()
                    fig.savefig(buf, format="png")
                    buf.seek(0)

                    url = "https://api.imgur.com/3/image"
                    headers = {"Authorization": "Client-ID " + client_id}
                    data = {"image": base64.b64encode(buf.read())}
                    response = requests.post(url, headers=headers, data=data)

                    if response.status_code == 200:
                        imgur_uploaded_link = response.json()["data"]["link"]
                        # print("Succesfully uploaded! Image URL is", imgur_uploaded_link)
                        return imgur_uploaded_link
                    else:
                        print("Could not upload to imgur")

                def type_check(input):
                    if isinstance(input, str):
                        return input
                    if isinstance(input, pd.DataFrame) or isinstance(input, pd.Series):
                        return input.to_markdown()

                df = pd.read_csv(io.StringIO(csv_data))
                print(df.head(1))

                #
                async def concat_stream_request(request, bot):
                    output_list = []
                    async for msg in stream_request(request, bot, request.access_key):
                        output_list.append(msg.text)
                    return output_list

                request.query[-1].content = self.apply_template(
                    df, request.query[-1].content
                )
                concatenated_msgs = await concat_stream_request(request, BASE_BOT)
                joined_messages = "".join(concatenated_msgs)
                code_blocks = re.findall(
                    r"```\s*python(.*?)```", joined_messages, re.DOTALL
                )

                print(joined_messages)
                print(f"{code_blocks=}")
                print(f"{len(code_blocks)=}")
                joined_code_blocks = "".join(code_blocks)
                f = StringIO()
                with redirect_stdout(f):
                    exec(joined_code_blocks)
                    exec("\nprint(output_df.to_markdown())")
                    exec("\nprint(upload(fig))")
                    ### check if user wanted a plot
                    # if "plt.plot" in joined_code_blocks:
                    # save fig
                    ## exec("\n")

                # print(os.listdir())
                #
                # def print_all_file_paths(directory):
                #     for root, dirs, files in os.walk(directory):
                #         for file in files:
                #             file_path = os.path.join(root, file)
                #             print(file_path)
                #
                #
                # fig = plt.figure()
                # plt.plot([1, 2, 3, 4])
                # plt.ylabel("some numbers")
                # plt.savefig("local_save_test.png")
                #
                # imgur_uploaded_link = upload(client_id, fig)
                #
                # print_all_file_paths("/root")
                # print(os.getcwd())
                print(plt)

                printed_output = f.getvalue()
                imgur_link = printed_output.strip().split("\n")[-1]
                printed_output_clean = (
                    "\n".join(printed_output.strip().split("\n")[:-1]) + "\n"
                )
                print(f"{imgur_link=}")
                print(f"{printed_output=}")
                yield PartialResponse(
                    text=f"## OUTPUT FROM RUNNING CODE: \n{printed_output_clean} \n\n\n### Explantion:\n{joined_messages} \n### PLOT!!! ![cat]({imgur_link})"
                )

    async def get_settings(self, setting: SettingsRequest) -> SettingsResponse:
        return SettingsResponse(
            server_bot_dependencies={BASE_BOT: 1, "DataTable": 1},
            allow_attachments=True,
            introduction_message="",
        )
