#  Moon-Userbot - telegram userbot
#  Copyright (C) 2020-present Moon Userbot Organization
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.

#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

import logging
import math
import time
import os
import re
import sys
import asyncio
import traceback
import importlib
import subprocess
from io import BytesIO
from types import ModuleType
from typing import Dict

from PIL import Image
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram import Client, errors, types, enums
from pyrogram.types import Message

from .misc import modules_help, prefix, requirements_list

META_COMMENTS = re.compile(r"^ *# *meta +(\S+) *: *(.*?)\s*$", re.MULTILINE)
interact_with_to_delete = []

def time_formatter(milliseconds: int) -> str:
    """Time Formatter"""
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = (
        (f"{str(days)} day(s), " if days else "")
        + (f"{str(hours)} hour(s), " if hours else "")
        + (f"{str(minutes)} minute(s), " if minutes else "")
        + (f"{str(seconds)} second(s), " if seconds else "")
        + (f"{str(milliseconds)} millisecond(s), " if milliseconds else "")
    )
    return tmp[:-2]

def humanbytes(size):
    """Convert Bytes To Bytes So That Human Can Read It"""
    if not size:
        return ""
    power = 2 ** 10
    raised_to_pow = 0
    dict_power_n = {0: "", 1: "Ki", 2: "Mi", 3: "Gi", 4: "Ti"}
    while size > power:
        size /= power
        raised_to_pow += 1
    return f"{str(round(size, 2))} {dict_power_n[raised_to_pow]}B"

async def edit_or_send_as_file(
    text: str,
    message: Message,
    client: Client,
    caption: str = "`Result!`",
    file_name: str = "result",
    parse_mode=enums.ParseMode.MARKDOWN,
):
    """Send As File If Len Of Text Exceeds Tg Limit Else Edit Message"""
    if not text:
        await message.edit("`Wait, What?`", parse_mode=enums.ParseMode.MARKDOWN)
        return
    if len(text) <= 1024:
        return await message.edit(text, parse_mode=parse_mode)
    await message.edit("`OutPut is Too Large, Sending As File!`", parse_mode=enums.ParseMode.MARKDOWN)
    file_names = f"{file_name}.text"
    open(file_names, "w").write(text)
    await client.send_document(message.chat.id, file_names, caption=caption)
    await message.delete()
    if os.path.exists(file_names):
        os.remove(file_names)
    return

def get_text(message: Message) -> [None, str]:
    """Extract Text From Commands"""
    text_to_return = message.text
    if message.text is None:
        return None
    if " " not in text_to_return:
        return None
    try:
        return message.text.split(None, 1)[1]
    except IndexError:
        return None

async def progress(current, total, message, start, type_of_ps, file_name=None):
    """Progress Bar For Showing Progress While Uploading / Downloading File - Normal"""
    now = time.time()
    diff = now - start
    if round(diff % 10.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff
        elapsed_time = round(diff) * 1000
        if elapsed_time == 0:
            return
        time_to_completion = round((total - current) / speed) * 1000
        estimated_total_time = elapsed_time + time_to_completion
        progress_str = "{0}{1} {2}%\n".format(
            "".join(["▰" for _ in range(math.floor(percentage / 10))]),
            "".join(["▱" for _ in range(10 - math.floor(percentage / 10))]),
            round(percentage, 2),
        )
        tmp = progress_str + "{0} of {1}\nETA: {2}".format(
            humanbytes(current), humanbytes(total), time_formatter(estimated_total_time)
        )
        if file_name:
            try:
                await message.edit(
                    "{}\n**File Name:** `{}`\n{}".format(type_of_ps, file_name, tmp, parse_mode=enums.ParseMode.MARKDOWN)
                )
            except FloodWait as e:
                await asyncio.sleep(e.x)
            except MessageNotModified:
                pass
        else:
            try:
                await message.edit(f"{type_of_ps}\n{tmp}", parse_mode=enums.ParseMode.MARKDOWN)
            except FloodWait as e:
                await asyncio.sleep(e.x)
            except MessageNotModified:
                pass

async def edit_or_reply(message, text, parse_mode=enums.ParseMode.MARKDOWN):
    """Edit Message If Its From Self, Else Reply To Message"""
    return await message.edit(text, parse_mode=parse_mode)

def text(message: types.Message) -> str:
    """Find text in `types.Message` object"""
    return message.text if message.text else message.caption


def restart() -> None:
    os.execvp(sys.executable, [sys.executable, "main.py"])


def format_exc(e: Exception, suffix="") -> str:
    traceback.print_exc()
    if isinstance(e, errors.RPCError):
        return (
            f"<b>Telegram API error!</b>\n"
            f"<code>[{e.CODE} {e.ID or e.NAME}] — {e.MESSAGE.format(value=e.value)}</code>\n\n<b>{suffix}</b>"
        )
    return (
        f"<b>Error!</b>\n"
        f"<code>{e.__class__.__name__}: {e}</code>\n\n<b>{suffix}</b>"
    )


def with_reply(func):
    async def wrapped(client: Client, message: types.Message):
        if not message.reply_to_message:
            await message.edit("<b>Reply to message is required</b>", parse_mode=enums.ParseMode.HTML)
        else:
            return await func(client, message)

    return wrapped


async def interact_with(message: types.Message) -> types.Message:
    """
    Check history with bot and return bot's response

    Example:
    .. code-block:: python
        bot_msg = await interact_with(await bot.send_message("@BotFather", "/start"))
    :param message: already sent message to bot
    :return: bot's response
    """

    await asyncio.sleep(1)
    # noinspection PyProtectedMember
    response = [
        msg
        async for msg in message._client.get_chat_history(
            message.chat.id, limit=1
        )
    ]
    seconds_waiting = 0

    while response[0].from_user.is_self:
        seconds_waiting += 1
        if seconds_waiting >= 5:
            raise RuntimeError("bot didn't answer in 5 seconds")

        await asyncio.sleep(1)
        # noinspection PyProtectedMember
        response = [
            msg
            async for msg in message._client.get_chat_history(
                message.chat.id, limit=1
            )
        ]

    interact_with_to_delete.append(message.id)
    interact_with_to_delete.append(response[0].id)

    return response[0]


def format_module_help(module_name: str, full=True):
    commands = modules_help[module_name]

    help_text = (
        f"<b>Help for |{module_name}|\n\nUsage:</b>\n"
        if full
        else "<b>Usage:</b>\n"
    )

    for command, desc in commands.items():
        cmd = command.split(maxsplit=1)
        args = f" <code>{cmd[1]}</code>" if len(cmd) > 1 else ""
        help_text += f"<code>{prefix}{cmd[0]}</code>{args} — <i>{desc}</i>\n"

    return help_text


def format_small_module_help(module_name: str, full=True):
    commands = modules_help[module_name]

    help_text = (
        f"<b>Help for |{module_name}|\n\nCommands list:\n"
        if full
        else "<b>Commands list:\n"
    )
    for command, desc in commands.items():
        cmd = command.split(maxsplit=1)
        args = f" <code>{cmd[1]}</code>" if len(cmd) > 1 else ""
        help_text += f"<code>{prefix}{cmd[0]}</code>{args}\n"
    help_text += (
        f"\nGet full usage: <code>{prefix}help {module_name}</code></b>"
    )

    return help_text


def import_library(library_name: str, package_name: str = None):
    """
    Loads a library, or installs it in ImportError case
    :param library_name: library name (import example...)
    :param package_name: package name in PyPi (pip install example)
    :return: loaded module
    """
    if package_name is None:
        package_name = library_name
    requirements_list.append(package_name)

    try:
        return importlib.import_module(library_name)
    except ImportError:
        completed = subprocess.run(
            [sys.executable, "-m", "pip", "install", package_name]
        )
        if completed.returncode != 0:
            raise AssertionError(
                f"Failed to install library {package_name} (pip exited with code {completed.returncode})",
                parse_mode=enums.ParseMode.HTML
            )
        return importlib.import_module(library_name)


def resize_image(
    input_img, output=None, img_type="PNG", size: int = 512, size2: int = None
):
    if output is None:
        output = BytesIO()
        output.name = f"sticker.{img_type.lower()}"

    with Image.open(input_img) as img:
        # We used to use thumbnail(size) here, but it returns with a *max* dimension of 512,512
        # rather than making one side exactly 512, so we have to calculate dimensions manually :(
        if size2 is not None:
            size = (size, size2)
        elif img.width == img.height:
            size = (size, size)
        elif img.width < img.height:
            size = (max(size * img.width // img.height, 1), size)
        else:
            size = (size, max(size * img.height // img.width, 1))

        img.resize(size).save(output, img_type)

    return output


async def load_module(
    module_name: str,
    client: Client,
    message: types.Message = None,
    core=False,
) -> ModuleType:
    if module_name in modules_help and not core:
        await unload_module(module_name, client)

    path = f"modules.{'custom_modules.' if not core else ''}{module_name}"

    with open(f"{path.replace('.', '/')}.py", encoding="utf-8") as f:
        code = f.read()
    meta = parse_meta_comments(code)

    packages = meta.get("requires", "").split()
    requirements_list.extend(packages)

    try:
        module = importlib.import_module(path)
    except ImportError as e:
        if core:
            # Core modules shouldn't raise ImportError
            raise

        if not packages:
            raise

        if message:
            await message.edit(
                f"<b>Installing requirements: {' '.join(packages)}</b>",
                parse_mode=enums.ParseMode.HTML
            )

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pip",
            "install",
            "-U",
            *packages,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=120)
        except asyncio.TimeoutError:
            if message:
                await message.edit(
                    "<b>Timeout while installed requirements. Try to install them manually</b>",
                    parse_mode=enums.ParseMode.HTML
                )
            raise TimeoutError("timeout while installing requirements") from e

        if proc.returncode != 0:
            if message:
                await message.edit(
                    f"<b>Failed to install requirements (pip exited with code {proc.returncode}). "
                    f"Check logs for futher info</b>",
                    parse_mode=enums.ParseMode.HTML
                )
            raise RuntimeError("failed to install requirements") from e

        module = importlib.import_module(path)

    for obj in vars(module).values():
        if type(getattr(obj, "handlers", [])) == list:
            for handler, group in getattr(obj, "handlers", []):
                client.add_handler(handler, group)

    module.__meta__ = meta

    return module


async def unload_module(module_name: str, client: Client) -> bool:
    path = f"modules.custom_modules.{module_name}"
    if path not in sys.modules:
        return False

    module = importlib.import_module(path)

    for obj in vars(module).values():
        for handler, group in getattr(obj, "handlers", []):
            client.remove_handler(handler, group)

    del modules_help[module_name]
    del sys.modules[path]

    return True


def parse_meta_comments(code: str) -> Dict[str, str]:
    try:
        groups = META_COMMENTS.search(code).groups()
    except AttributeError:
        return {}

    return {groups[i]: groups[i + 1] for i in range(0, len(groups), 2)}