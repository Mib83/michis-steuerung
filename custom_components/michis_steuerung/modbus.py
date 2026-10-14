"""Small, bounded Modbus TCP reader for DHT22 Klima holding registers 0–2."""
import asyncio
import struct


def decode_measurements(registers):
    raw, humidity, valid = registers
    signed = raw if raw < 32768 else raw - 65536
    if valid != 3 or signed == -32768 or humidity == 65535:
        raise ValueError('DHT22 meldet ungültige Messwerte')
    temperature, humidity = signed / 100, humidity / 100
    if not -40 <= temperature <= 80 or not 0 <= humidity <= 100:
        raise ValueError('DHT22-Messwerte außerhalb des Messbereichs')
    return temperature, humidity


async def _exchange(host, port, unit):
    writer = None
    try:
        reader, writer = await asyncio.open_connection(host, port)
        # Transaction 1, protocol 0, length 6 (unit + function/address/count).
        writer.write(struct.pack('>HHHBBHH', 1, 0, 6, unit, 3, 0, 3))
        await writer.drain()
        header = await reader.readexactly(7)
        transaction, protocol, length, reply_unit = struct.unpack('>HHHB', header)
        if transaction != 1 or protocol != 0 or reply_unit != unit or not 2 <= length <= 254:
            raise ValueError('Ungültige Modbus-Antwort')
        payload = await reader.readexactly(length - 1)
        if payload[0] == 0x83:
            raise ValueError(f'Modbus-Fehler {payload[1]}')
        if payload[:2] != b'\x03\x06' or len(payload) != 8:
            raise ValueError('Unerwartete Modbus-Registerantwort')
        return decode_measurements(struct.unpack('>HHH', payload[2:]))
    finally:
        if writer is not None:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 1)
            except (OSError, asyncio.TimeoutError):
                pass


async def read_climate(host, port=502, unit=1):
    return await asyncio.wait_for(_exchange(host, port, unit), 4)
