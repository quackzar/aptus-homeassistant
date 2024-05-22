from __future__ import annotations
import re
from enum import Enum
from typing import Tuple
import aiohttp
from aiohttp import ClientSession
from bs4 import BeautifulSoup

# Base header for the client to use.
# This properly doesn't matter,
# but since we are *pretending* to be the JS client
# it should properly match a real browser.
base_headers = {
    'Accept': '*/*',
    'X-Requested-With': 'XMLHttpRequest',
    'Sec-Ch-Ua-Mobile': '?0',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5845.97 Safari/537.36',
    'Sec-Ch-Ua-Platform': '""',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Dest': 'empty',
    'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
}


class DoorStatus(Enum):
    LOCKED = 1
    UNLOCKED = 2
    JAMMED = 3
    UNKNOWN = 4


class BatteryStatus(Enum):
    LOW = 1
    NORMAL = 2

class DoorClient:
    host: str
    username: str
    password: str

    headers: dict[str, str]
    session: ClientSession
    door_id: str

    def __init__(self, host: str, username: str, password: str) -> None:
        self.host = host
        self.username = username
        self.password = password
        headers = base_headers
        headers['Host'] = self.host
        headers['Referer'] = self.host + '/AptusPortal/Lock'
        self.session = ClientSession()


    async def close(self):
        await self.session.close()

    async def login(self):
        ok, msg = await login(self.session, self.username, self.password, self.host)
        if ok:
            self.door_id = msg
        return ok, msg

    async def lock(self) -> DoorStatus:
        resp = await lock_door(self.session, self.host)
        if resp.status != 200:
            return DoorStatus.JAMMED
        return DoorStatus.LOCKED

    async def unlock(self) -> DoorStatus:
        resp = await unlock_door(self.session, self.host, self.password)
        if resp.status != 200:
            return DoorStatus.JAMMED
        return DoorStatus.UNLOCKED

    async def unlock_frontdoor(self) -> bool:
        resp = await unlock_entry_door(self.session, self.host, self.door_id)
        if resp.status != 200:
            return False
        else:
            return True

    async def status_update(self) -> Tuple[DoorStatus, BatteryStatus]:
        await set_status_temp(self.session, self.host)
        resp = await door_status(self.session, self.host)
        try:
            data = await resp.json()
        except Exception:
            return (DoorStatus.UNKNOWN, BatteryStatus.NORMAL)

        battery = BatteryStatus.LOW if data['BatteryLevelLow'] else BatteryStatus.NORMAL
        status = DoorStatus.LOCKED if data['IsClosedAndLocked'] else DoorStatus.UNLOCKED
        if data['StatusText'] == 'Door is open':
            status = DoorStatus.UNLOCKED
        return status, battery

    async def camera(self):
        # TODO: Reverse-engineer the camera properly.
        return await get_camera(self.session, self.host, self.door_id)



def enc(msg: str, key: int):
    # replicating the js version
    # very bad crypto
    result = ''
    for m in msg:
        char = ord(m)
        result += chr(char ^ key)
    return result

# This extracts the secrets that the server puts in the HTML file,
# which the JS client reads, we do not have a DOM so we will just parse it.
async def shake_hands(session: aiohttp.ClientSession, host: str):
    # Reuse existing session if given

    # Generate session ID
    headers = base_headers
    headers['Host'] = host
    await session.get(
            f"https://{host}/AptusPortal/Account/Login?ReturnUrl=%2fAptusPortal%2f",
            headers=headers,
            )
    response = await session.get(
            f"https://{host}/AptusPortal/Account/Login?ReturnUrl=%2fAptusPortal%2f",
            headers=headers,
            )
    soup = BeautifulSoup(await response.text(), features="html.parser")
    hidden = soup.find_all("input", type="hidden")
    salt = 0
    req_ver_token = ""
    for tag in hidden:
        name = tag["name"]
        value = tag["value"]
        if name == "__RequestVerificationToken":
            req_ver_token = value
        if name == "PasswordSalt":
            salt = int(value)
    return (salt, req_ver_token)


async def login(session: aiohttp.ClientSession, username: str, password: str, host: str) -> Tuple[bool, str]:
    salt, req_ver_token = await shake_hands(session, host)
    data = {
            'DeviceType': 'PC',
            'DesktopSelected': 'true',
            '__RequestVerificationToken': req_ver_token,
            'UserName': username,
            'Password': password,
            'PwEnc': enc(password, salt),
            'PasswordSalt': str(salt),
            }
    response = await session.post(
            f'https://{host}/AptusPortal/Account/Login?ReturnUrl=%2fAptusPortal%2f',
            headers=base_headers,
            data=data,
            )

    # Escalate permissions (very important!)
    response = await session.get(
            f"https://{host}/AptusPortal/Lock",
            headers=base_headers
            )

    msg: str = await response.text()
    if response.status != 200:
        return (response.status == 200, msg)

    match = re.search(r'UnlockEntranceDoor\((\d+)\)', msg)
    if match:
        door_id = match.group(1)
        return (True, door_id)
    return (False, 'No door id found')




#
# Boilerplate to simplify calls to the server
# Could properly be inlined
#

async def lock_door(session: aiohttp.ClientSession, host: str) -> aiohttp.ClientResponse:
    response = session.get(
            f'https://{host}/AptusPortal/Lock/LockDoormanLock',
            headers=base_headers,
            )
    return await response

async def unlock_door(session: aiohttp.ClientSession, host: str, password: str) -> aiohttp.ClientResponse:
    params = { 'code': password }
    response = session.get(
            f'https://{host}/AptusPortal/Lock/UnlockDoormanLock',
            params=params,
            headers=base_headers,
            )
    return await response


async def unlock_entry_door(session: aiohttp.ClientSession, host: str, door_id: str) -> aiohttp.ClientResponse:
    response = session.get(
            f'https://{host}/AptusPortal/Lock/UnlockEntryDoor/{door_id}',
            headers=base_headers,
            )
    return await response

async def door_status(session: aiohttp.ClientSession, host: str) -> aiohttp.ClientResponse:
    response = session.get(
            f'https://{host}/AptusPortal/LockAsync/DoormanLockStatus',
            headers=base_headers,
            )
    return await response


async def set_status_temp(session: aiohttp.ClientSession, host: str) -> aiohttp.ClientResponse:
    response = session.get(
            f'https://{host}/AptusPortal/Lock/SetLockStatusTempData',
            headers=base_headers,
            )
    return await response


async def poll_ongoing_call(session: aiohttp.ClientSession, host: str) -> aiohttp.ClientResponse:
    params = {
            '_': '1692822984518', # initial UNIX TIMESTAMP in milliseconds
            }
    # repeated every 20 seconds
    response = session.get(
            f'https://{host}/AptusPortal/Lock/PollOngingCall',
            headers=base_headers,
            params=params,

            )
    return await response

async def get_camera(session: aiohttp.ClientSession, host: str, door_id: str) -> aiohttp.ClientResponse:
    response = session.get(
            f'https://{host}/AptusPortal/Lock/WebCameraImageGrabber?doorId={door_id}',
            headers=base_headers,
            )
    return await response

