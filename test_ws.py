import asyncio, websockets
async def test():
    try:
        async with websockets.connect('wss://boaster-fencing-guise.ngrok-free.dev/ws?token=fake', extra_headers={'ngrok-skip-browser-warning': 'true'}) as ws:
            print('Connected!')
            msg = await ws.recv()
            print(msg)
    except Exception as e:
        print('Error:', e)
asyncio.run(test())
