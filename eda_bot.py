import os
from pprint import pprint
import io
import re
import base64
import logging
from typing_extensions import override
import requests
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO, StringIO
from contextlib import redirect_stdout
from typing import AsyncIterable, Optional
from fastapi_poe import PoeBot
from fastapi_poe.client import stream_request
from fastapi_poe.types import (
    PartialResponse,
    ProtocolMessage,
    QueryRequest,
    SettingsRequest,
    SettingsResponse,
)
from modal import Stub, Secret

logging.basicConfig(format="%(asctime)s - %(message)s", level=logging.INFO)
# BASE_BOT = "GPT-3.5-Turbo"
BASE_BOT = "GPT-4"
stub = Stub()


@stub.function(secret=Secret.from_name("poe-access-key"))
def upload_to_imgur(fig) -> Optional[str]:
    client_id = os.environ["IMGUR_KEY"]
    buf = BytesIO()
    fig.savefig(buf, format="png")
    buf.seek(0)

    url = "https://api.imgur.com/3/image"
    headers = {"Authorization": f"Client-ID {client_id}"}
    data = {"image": base64.b64encode(buf.read())}
    response = requests.post(url, headers=headers, data=data)

    if response.status_code == 200:
        imgur_uploaded_link = response.json()["data"]["link"]
        print(imgur_uploaded_link)
        print(type(imgur_uploaded_link))
        logging.info(f"Succesfully uploaded! Image URL is {imgur_uploaded_link}")
        return imgur_uploaded_link
    else:
        logging.info("Could not upload to imgur")
        return None


def type_check(input):
    """
    handling return type of running generated code. If result is just a string, then return that.
    If its a pandas type then return as a markdown table.
    """
    if isinstance(input, (pd.DataFrame, pd.Series)):
        input = input.to_markdown()
    return input


def update_temperature(
    request: QueryRequest, new_temperature: float = 0.2
) -> QueryRequest:
    logging.info(f"current temperature: {request.temperature}")
    request.temperature = new_temperature
    logging.info(f"updated temperature: {request.temperature}")
    return request


def check_final_output_length(response):
    """
    there is a 100000 character limit for responses.
    most likely the character limit will be hit because we are printing the resulting df as a table.
    we need to truncate the result if it is too long.
    """
    # The issue is that we might be printing markdown tables and its not possible to know the size of the
    # table in terms of characters.
    ...


def set_system_prompt(request: QueryRequest) -> QueryRequest:
    system_prompt = """You are a python data analysis expert. You only know how to use tools like pandas, matplotlib and numpy. \
    You are part of a chatbot system that allows users to ask questions about their data. \
    You help with writing pandas queries that translate natural language queries that users ask. \
    The code that you generate will be run against the data that the user submits (a .csv file). \
    The csv file that the user submits has already been loaded into a pandas dataframe -> df = pd.read_csv(*user's file*). \
    Here are the import statements that have been run: import pandas as pd, import matplotlib.pyplot as plt, import numpy as np. \
    DO NOT import any libraries. \
    Only output 1 version of the code. Do not output any alternative ways of writing the code. \
    Return the code as one large contiguous code block. \
    Keep in mind that the code you return will be run using python's exec() function. \
    The user has no experience writing code so be as helpful as possible I am begging you."""
    if request.query[0].role != "system":
        # no system prompt set
        system_message = ProtocolMessage(role="system", content=system_prompt)
        request.query = [system_message] + request.query
    return request


def apply_template(df: pd.DataFrame, query: str) -> str:
    return f"""You are given a pandas dataframe with the variable name df. Follow the query provided and generate the reasoning to answer the question. \
        Finally, generate the correct code that answer the question and save the output to a new variable called output_df. \
        Also, appropriately plot the resulting dataframe using matplotlib. run fig = plt.figure() first before adding the title or axis. Do not do plt.show(). \
        You are also provided some details of the dataframe. The columns of the dataframe are {df.columns}.\
        The head of the dataframe is {df.head()} Query: {query}\
        If you are returning a dataframe as the result of the query, ensure that you return at most 20 rows of data as there are restrictions to \
        the size of data that can be returned.
        """


async def concat_stream_request(request, bot):
    output_list = []
    async for msg in stream_request(request, bot, request.access_key):
        output_list.append(msg.text)
    return output_list


def check_attachement_on_any_message(request: QueryRequest):
    return any([len(msg.attachments) > 0 for msg in request.query])


def find_last_attachment(request: QueryRequest):
    for msg in request.query[::-1]:
        if len(msg.attachments) > 0:
            return msg.attachments[0]


def code_runner(code: str, request: QueryRequest):
    f = StringIO()
    try:
        with redirect_stdout(f):
            exec(code)
            exec("\nprint(type_check(output_df))")
            if "--plot" in request.query[-1].content:
                exec("\nprint(upload_to_imgur(fig))")
    except Exception as e:
        logging.info(f"Error when running code: {e}")
        return f"Error: {e}"
    printed_output = f.getvalue()
    return "\n".join(printed_output.strip().split("\n")[:-1]) + "\n"


def modal_test_exec():
    """
    This function is to determine the exact behaviour of the python exec() in the modal container.
    """
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    code = """
    x = 1
    y = 2
    print(x+y)
    print(df)
    """
    f = StringIO()
    with redirect_stdout(f):
        exec(code)
    printed_output = f.getvalue()
    return printed_output


class EDA_bot(PoeBot):
    @override
    async def get_settings(self, setting: SettingsRequest) -> SettingsResponse:
        return SettingsResponse(
            server_bot_dependencies={BASE_BOT: 1},
            allow_attachments=True,
            introduction_message="""
            I am a Data Analyzer! Please upload a csv file and the query you want to input. \
            Add --plot in your query to display a pyplot. \
            I will generate the code for you to run against your data and return the output. \
            If you encounter any issues when waiting for me to respond, kindly rerun the query. \
            I am still in beta so please be patient with me. \
            """,
        )

    @override
    async def get_response(
        self, request: QueryRequest
    ) -> AsyncIterable[PartialResponse]:
        request = update_temperature(request)
        request = set_system_prompt(request)
        pprint(request.query)
        if check_attachement_on_any_message(request):
            logging.info("There is an attachment")
            attachment_info = find_last_attachment(request)
            attachment_url = attachment_info.url
            response = requests.get(attachment_url)
            if response.status_code == 200:
                # The request was successful, so proceed to read the CSV content
                csv_data = response.text
            else:
                # Handle the case when the request was not successful
                logging.info(
                    f"Failed to download CSV. Status code: {response.status_code}"
                )
                csv_data = None
            if csv_data:
                df = pd.read_csv(io.StringIO(csv_data))
                logging.info(f"df head: {df.head(1)}")

                request.query[-1].content = apply_template(
                    df, request.query[-1].content
                )
                concatenated_msgs = await concat_stream_request(request, BASE_BOT)
                joined_messages = "".join(concatenated_msgs)
                code_blocks = re.findall(
                    r"```\s*python(.*?)```", joined_messages, re.DOTALL
                )
                joined_code_blocks = "".join(code_blocks)

                logging.info(joined_messages)
                logging.info(f"{code_blocks=}")
                logging.info(f"{len(code_blocks)=}")
                printed_output = code_runner(joined_code_blocks, request)
                if printed_output.startswith("Error"):
                    yield PartialResponse(
                        text=f"*there were issues running the code but here is the code* \n ## Generated Code: \n\n {printed_output}"
                    )
                print(f"{printed_output=}")
                if "--plot" in request.query[-1].content:
                    imgur_link = printed_output.strip().split("\n")[-1]
                    logging.info(f"{imgur_link=}")
                    printed_output_clean = (
                        "\n".join(printed_output.strip().split("\n")[:-1]) + "\n"
                    )
                    yield PartialResponse(
                        text=f"## OUTPUT FROM RUNNING CODE: \n{printed_output_clean} \n\n\n### Explanation:\n{joined_messages}\n ### PLOT: ![cat]({imgur_link})"
                    )
                else:
                    yield PartialResponse(
                        text=f"## OUTPUT FROM RUNNING CODE: \n{printed_output} \n\n\n### Explanation:\n{joined_messages}\n"
                    )
        else:
            async for msg in stream_request(request, BASE_BOT, request.access_key):
                yield msg
