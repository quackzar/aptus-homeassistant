#
# Test script to check if the API emulation works
#

from door import DoorClient
import argparse
import asyncio
import os


async def main():
    host = os.environ['APTUS_HOST']
    username = os.environ['APTUS_USERNAME']
    password = os.environ['APTUS_PASSWORD']
    parser = argparse.ArgumentParser(
                        prog='Door Tester',
                        description='Tests the door',
                        epilog='Aptus Not Affiliated')
    parser.add_argument('command')
    args = parser.parse_args()
    client = DoorClient(host, username, password)

    succ, desc = await client.login()
    if succ:
        print("Succesfully logged in")
    else:
        print(f"Failed to login: {desc}")
        exit(-1)

    match args.command:
        case "unlock":
            res = await client.unlock()
            print(res)
            pass
        case "lock":
            res = await client.lock()
            print(res)
            pass
        case "status":
            door, battery = await client.status_update()
            print(f"Door: {door}")
            print(f"Battery: {battery}")
            pass
        case "frontdoor":
            res = await client.unlock_frontdoor()
            print(res)
            pass
        case "camera":
            res = await client.camera()
            print(res)
            pass
        case _:
            print(f"unhandled command '{args.command}'")

    await client.close()
    print('quitting')



asyncio.run(main())
