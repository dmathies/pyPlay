import socket
import struct
import re
from re import match
from enum import IntEnum
from typing import Any
import sys
if sys.version_info >= (3, 10):
    from typing import TypeAlias
else:
    from typing_extensions import TypeAlias

from numpy import number

# from artnet import ART_NET_PORT


ART_NET_PORT = 6454
ArtNetFieldDict: TypeAlias = dict[str, Any] | None


# Constants for Art-Net
ART_NET_HEADER = b"Art-Net\x00"
ART_NET_VERSION = struct.pack(">H", 14)  # Protocol version
ART_NET_OEM = struct.pack("<H", 0x00FF)  # OEM code OemUnknown 0x00ff
ART_NET_ESTA_MAN = struct.pack("<H", 0)  # ESTA Manufacturer code


class OpCode(IntEnum):
    ArtPoll = 0x2000
    ArtPollReply = 0x2100
    ArtCommand = 0x2400
    ArtTrigger = 0x9900
    ArtDmx = 0x5000
    ArtNzs = 0x5100
    ArtSync = 0x5200
    ArtIpProg = 0xF800
    ArtIpProgReply = 0xF900
    ArtAddress = 0x6000
    ArtTodRequest = 0x8000
    ArtTodData = 0x8100
    ArtTodControl = 0x8200
    ArtRdm = 0x8300
    ArtRdmSub = 0x8400
    ArtTimeCode = 0x9700
    ArtUNKNOWN = 0xFFFF


def is_artnet(data: bytes) -> bool:
    return data.startswith(ART_NET_HEADER)


def parse_header(data: bytes) -> OpCode | None:
    if is_artnet(data) and len(data) >= 10:
        op_code_from_byte = struct.unpack("<H", data[8:10])[0]
        try:
            return OpCode(op_code_from_byte)
        except ValueError:
            return OpCode.ArtUNKNOWN
    else:
        return None


def parse_poll(data: bytes) -> ArtNetFieldDict:
    if len(data) < 14:
        return None

    # If the data is less than 22 bytes, pad it with zeros.
    if len(data) < 22:
        data += bytes(22 - len(data))

    reply = dict(
        ProtVer=struct.unpack(">H", data[10:12])[0],
        Flags=[bool(data[12] >> i & 1) for i in range(8)],
        DiagPriority=data[13],
        TargetPort=[
            struct.unpack("<H", data[16:18])[0],
            struct.unpack("<H", data[14:16])[0],
        ],
        EstaMan=struct.unpack("<H", data[18:20])[0],
        Oem=struct.unpack("<H", data[20:22])[0],
    )

    return reply


def parse_poll_reply(data: bytes) -> ArtNetFieldDict:
    if len(data) < 239:
        return None

    reply = dict(
        IpAdress=".".join(map(str, struct.unpack("BBBB", data[10:14]))),
        PortNumber=struct.unpack("<H", data[14:16])[0],
        VersInfo=struct.unpack("<H", data[16:18])[0],
        NetSwitch=data[18],
        SubSwitch=data[19],
        Oem=struct.unpack("<H", data[20:22])[0],
        UbeaVersion=data[22],
        Status1=data[23],
        EstaMan=struct.unpack("<H", data[24:26])[0],
        ShortName=data[26:44].strip(b"\0").decode(),
        LongName=data[44:108].strip(b"\0").decode(),
        NodeReport=data[108:172].strip(b"\0").decode(),
        NumPorts=struct.unpack("<H", data[172:174])[0],
        PortTypes=list(struct.unpack("BBBB", data[174:178])),
        GoodInput=list(struct.unpack("BBBB", data[178:182])),
        GoodOutput=list(struct.unpack("BBBB", data[182:186])),
        SwIn=list(struct.unpack("BBBB", data[186:190])),
        SwOut=list(struct.unpack("BBBB", data[190:194])),
        SwVideo=data[194],
        SwMacro=data[195],
        SwRemote=data[196],
        Spare1=data[197],
        Spare2=data[198],
        Spare3=data[199],
        Style=data[200],
        Mac=":".join(
            map(lambda x: format(x, "02x"), struct.unpack("BBBBBB", data[201:207]))
        ),
        BindIp=".".join(map(str, struct.unpack("BBBB", data[207:211]))),
        BindIndex=data[211],
        Status2=data[212],
        Filler=data[213:239].strip(b"\0"),
    )

    return reply


def parse_artdmx(data: bytes) -> ArtNetFieldDict:
    if len(data) < 18:
        return None

    reply = dict(
        ProtVer=struct.unpack("<H", data[10:12])[0],
        Sequence=data[12],
        Physical=data[13],
        Universe=struct.unpack("<H", data[14:16])[0],
        Length=struct.unpack(">H", data[16:18])[0],
        Data=data[18:],
    )

    return reply


def parse_nzs(data: bytes) -> ArtNetFieldDict:
    if len(data) < 18:
        return None

    reply = dict(
        ProtVer=struct.unpack("<H", data[10:12])[0],
        Sequence=data[12],
        StartCode=data[13],
        Universe=struct.unpack("<H", data[14:16])[0],
        Length=struct.unpack(">H", data[16:18])[0],
        Data=data[18:],
    )

    return reply


def parse_sync(data: bytes) -> ArtNetFieldDict:
    if len(data) < 13:
        return None

    reply = dict(
        ProtVer=struct.unpack("<H", data[10:12])[0],
        Aux1=data[12],
        Aux2=data[13],
    )

    return reply


def parse_trigger(data: bytes) -> ArtNetFieldDict:
    if len(data) < 18:
        return None

    reply = dict(
        ProtVer=struct.unpack("<H", data[10:12])[0],
        Oem=struct.unpack("<H", data[14:16])[0],
        Key=data[16],
        SubKey=data[17],
        Data=data[18:],
    )

    return reply


def parse_ip_prog(data: bytes) -> ArtNetFieldDict:
    if len(data) < 32:
        return None

    reply = dict(
        ProtVer=struct.unpack("<H", data[10:12])[0],
        Filler1=data[12],
        Filler2=data[13],
        Command=data[14],
        Filler4=data[15],
        ProgIp=".".join(map(str, struct.unpack("BBBB", data[16:20]))),
        ProgSm=".".join(map(str, struct.unpack("BBBB", data[20:24]))),
        ProgPort=struct.unpack("<H", data[24:26])[0],
        ProgDg=".".join(map(str, struct.unpack("BBBB", data[24:28]))),
        Spare=data[28:],
    )

    return reply


def parse_ip_prog_reply(data: bytes) -> ArtNetFieldDict:
    if len(data) < 34:
        return None

    reply = dict(
        ProtVer=struct.unpack("<H", data[10:12])[0],
        Filler1=data[12],
        Filler2=data[13],
        Filler3=data[14],
        Filler4=data[15],
        ProgIp=".".join(map(str, struct.unpack("BBBB", data[16:20]))),
        ProgSm=".".join(map(str, struct.unpack("BBBB", data[20:24]))),
        ProgPort=struct.unpack("<H", data[24:26])[0],
        Status=data[26],
        Spare2=data[27],
        ProgDg=".".join(map(str, struct.unpack("BBBB", data[28:32]))),
        Spare7=data[32],
        Spare8=data[33],
    )

    return reply


def parse_address(data: bytes) -> ArtNetFieldDict:
    if len(data) < 107:
        return None

    reply = dict(
        ProtVer=struct.unpack("<H", data[10:12])[0],
        NetSwitch=data[12],
        BindIndex=data[13],
        ShortName=data[14:32].decode().strip("\0"),
        LongName=data[32:96].decode().strip("\0"),
        SwIn=list(struct.unpack("BBBB", data[96:100])),
        SwOut=list(struct.unpack("BBBB", data[100:104])),
        SubSwitch=data[104],
        AcnPriority=data[105],
        Command=data[106],
    )

    return reply


def parse_command(data: bytes) -> ArtNetFieldDict:
    if len(data) < 14:
        return None

    reply = dict(
        ProtVer=struct.unpack("<H", data[10:12])[0],
        EstaMan=struct.unpack("<H", data[12:14])[0],
        Length=struct.unpack("<H", data[14:16])[0],
        Command=data[16:].decode().strip("\0"),
    )

    """
    Command
    - "SwoutText=Playback&" re-programme the label ArtPollReply->Swout
    - "SwinText=Record&" re-programme the label ArtPollReply->Swout
    """

    return reply


def parse_tod_request(data: bytes) -> ArtNetFieldDict:
    """
    Parses an ArtTodRequest packet.

    Expected layout (22 bytes total):
      - Bytes 0-7: "Art-Net\x00" header
      - Bytes 8-9: OpCode (0x8000)
      - Bytes 10-11: Protocol Version (big-endian)
      - Bytes 12-21: Spare (10 bytes)
    """
    if len(data) < 22:
        return None

    prot_ver = struct.unpack(">H", data[10:12])[0]
    spare = data[12:22]
    reply = dict(
        ProtVer=prot_ver,
        Spare=spare,
    )
    return reply


def parse_tod_data(data: bytes) -> ArtNetFieldDict:
    """
    Parses an ArtTodData packet.

    Expected layout:
      - Bytes 0-7: "Art-Net\x00" header
      - Bytes 8-9: OpCode (0x8001)
      - Bytes 10-11: Protocol Version (big-endian)
      - Byte 12: Sequence
      - Byte 13: Physical port
      - Bytes 14-15: Data length (big-endian)
      - Bytes 16 onward: TOD data payload (of given length)
    """
    if len(data) < 16:
        return None
    prot_ver = struct.unpack(">H", data[10:12])[0]
    sequence = data[12]
    physical = data[13]
    data_length = struct.unpack(">H", data[14:16])[0]
    if len(data) < 16 + data_length:
        return None
    tod_data = data[16 : 16 + data_length]
    reply = dict(
        ProtVer=prot_ver,
        Sequence=sequence,
        Physical=physical,
        DataLength=data_length,
        Data=tod_data,
    )
    return reply


def parse_tod_control(data: bytes) -> ArtNetFieldDict:
    """
    Parses an ArtTodControl packet.

    Expected layout (14 bytes total):
      - Bytes 0-7: "Art-Net\x00" header
      - Bytes 8-9: OpCode (0x8002)
      - Bytes 10-11: Protocol Version (big-endian)
      - Byte 12: Command
      - Byte 13: Spare
    """
    if len(data) < 14:
        return None
    prot_ver = struct.unpack(">H", data[10:12])[0]
    command = data[12]
    spare = data[13]
    reply = dict(
        ProtVer=prot_ver,
        Command=command,
        Spare=spare,
    )
    return reply


# Dictionary of parsers
ARTNET_REPLY_PARSER = {
    OpCode.ArtPoll: parse_poll,
    OpCode.ArtPollReply: parse_poll_reply,
    OpCode.ArtTrigger: parse_trigger,
    OpCode.ArtDmx: parse_artdmx,
    OpCode.ArtNzs: parse_nzs,
    OpCode.ArtSync: parse_sync,
    OpCode.ArtIpProg: parse_ip_prog,
    OpCode.ArtIpProgReply: parse_ip_prog_reply,
    OpCode.ArtAddress: parse_address,
    OpCode.ArtCommand: parse_command,
    OpCode.ArtTodRequest: parse_tod_request,
    OpCode.ArtTodData: parse_tod_data,
    OpCode.ArtTodControl: parse_tod_control,
    # OpCode.ArtRdm: parse_rdm,
}


def pack_ip(
    dhcp: bool = False,
    prog_ip: str | None = None,
    prog_sm: str | None = None,
    prog_gw: str | None = None,
    set_default: bool = False,
    prog_port: int | None = None,
) -> bytes:
    # Convert IP, subnet mask, and gateway to bytes
    ip_bytes = (
        struct.pack("BBBB", *map(int, prog_ip.split(".")))
        if prog_ip
        else b"\x00\x00\x00\x00"
    )
    sm_bytes = (
        struct.pack("BBBB", *map(int, prog_sm.split(".")))
        if prog_sm
        else b"\x00\x00\x00\x00"
    )
    gw_bytes = (
        struct.pack("BBBB", *map(int, prog_gw.split(".")))
        if prog_gw
        else b"\x00\x00\x00\x00"
    )

    # Set the command byte (bit 0 is for DHCP, bits 1-7 are reserved)
    # If all bits are clear, this is an enquiry only.
    #   7   Set to enable any programming.
    #   6   Set to enable DHCP (if set ignore lower bits).
    #   5   Not used, transmit as zero
    #   4   Program Default gateway
    #   3   Set to return all three parameters to default
    #   2   Program IP Address
    #   1   Program Subnet Mask
    #   0   Program Port

    command = 0

    if dhcp:
        command |= 1 << 6
    else:
        if prog_gw:
            command |= 1 << 4

        if set_default:
            command |= 1 << 3

        if prog_ip:
            command |= 1 << 2

        if prog_sm:
            command |= 1 << 1

        if prog_port is not None:
            command |= 1 << 0

    port_bytes = struct.pack("<H", prog_port if prog_port is not None else 0)

    if command > 0:
        command |= 1 << 7

    command_byte = struct.pack("<B", command)

    op_code = struct.pack("<H", OpCode.ArtIpProg)
    packet = (
        ART_NET_HEADER
        + op_code
        + ART_NET_VERSION
        + b"\x00" * 2  # Filler 1 + 2
        + command_byte  # Command
        + b"\x00"  # Filler 4
        + ip_bytes  # Programmed IP
        + sm_bytes  # Programmed subnet mask
        + port_bytes  # Programmed Port (Deprecated)
        + gw_bytes  # Programmed gateway
        + b"\x00" * 4  # Spare
    )

    return packet


def pack_address(
    net: int, sub: int, universe: int, port_name: str = "", long_name: str = ""
) -> bytes:
    if not (0 <= net <= 127):
        raise ValueError("Net must be between 0 and 127")
    if not (0 <= sub <= 15):
        raise ValueError("Sub must be between 0 and 15")
    if not (0 <= universe <= 15):
        raise ValueError("Universe must be between 0 and 15")

    command_byte = b"\x00"

    # universe15bit = (net << 8) | (subnet << 4) | universe4bit
    # Bit 0-3 -> universe4bit
    # Bit 4-7 -> subnet
    # Bit 14-8 -> net
    # 15 bit Port-Address in NetSwitch, SubSwitch and SwIn[] or SwOut[]
    # Their values are ignored unless bit 7 is high.
    # I.e. to program a value 0x07, send the value as 0x87.

    # Universe, Net and SubNet
    net_switch = net & 0b1111111
    net_switch_byte = struct.pack("<B", net_switch)

    sub_switch = 1 << 7 | sub & 0b1111
    sub_switch_byte = struct.pack("<B", sub_switch)

    sw_in = 1 << 7 | universe & 0b1111
    sw_in_byte = struct.pack("<B", sw_in)

    sw_out_byte = sw_in_byte

    port_name_byte = port_name.encode("ascii")
    if len(port_name_byte) > 17:
        port_name_byte = port_name_byte[:17]
    port_name_byte += b"\x00" * (18 - len(port_name_byte))

    long_name_byte = long_name.encode("ascii")
    if len(long_name_byte) > 63:
        long_name_byte = long_name_byte[:63]
    long_name_byte += b"\x00" * (64 - len(long_name_byte))

    op_code = struct.pack("<H", OpCode.ArtAddress)
    packet = (
        ART_NET_HEADER
        + op_code
        + ART_NET_VERSION
        + net_switch_byte  # Net switch: Bits 14-8 in bottom 7 bits
        + b"\x00"  # Bind index
        + port_name_byte  # Short name
        + long_name_byte  # Long name
        + sw_in_byte  # SwIn1: Bits 3-0 for input port in bottom 4 bits
        + b"\x00"  # SwIn2
        + b"\x00"  # SwIn3
        + b"\x00"  # SwIn4
        + sw_out_byte  # SwOut1: Bits 3-0 for output port in bottom 4 bits
        + b"\x00"  # SwOut2
        + b"\x00"  # SwOut3
        + b"\x00"  # SwOut4
        + sub_switch_byte  # Sub switch: Bits 7-4 in bottom 4 bits
        + b"\x00"  # AcnPriority
        + command_byte  # Command
    )

    return packet


def pack_poll() -> bytes:
    """
    Bit 0:  deprecated
        1:  0 = Only respond to ArtPoll or ArtAddress
            1 = ArtPollReply on Node change.
        2:  0 = Do not send diagnostics
            1 = Send diagnostics message
        3:  0 = Diagnostics messages are broadcast
            1 = Diagnostics messages are unicast
        4:  0 = Enable VLC transmission
            1 = Disable VLC transmission
        5:  0 = Disable Targeted Mode
            1 = Enable Targeted Mode
        6-7:Unused, transmit as zero
    """
    flags = b"\x00"
    # The lowest priority of diagnostics message to be sent
    diag_prio = b"\x00"
    # If Targeted Mode is active
    # Top of range of Port-Addresses to be tested
    target_port_address_top = struct.pack("<H", 0)
    # Bottom range
    target_port_address_bottom = struct.pack("<H", 0)

    op_code = struct.pack("<H", OpCode.ArtPoll)
    packet = (
        ART_NET_HEADER
        + op_code
        + ART_NET_VERSION
        + flags
        + diag_prio
        + target_port_address_top
        + target_port_address_bottom
        + ART_NET_ESTA_MAN
        + ART_NET_OEM
    )

    return packet


def pack_dmx(universe15bit: int, seq: int, dmx_data: bytes) -> bytes:
    # Sequence, physical and universe
    sequence = struct.pack("<B", seq)
    physical = struct.pack("<B", 0)
    universe = struct.pack("<H", universe15bit)

    # size = 512
    size = len(dmx_data)

    if size > 512:
        raise ValueError("data too long")

    # Length of DMX data
    dmx_length = struct.pack(">H", size)

    # OpCode
    op_code = struct.pack("<H", OpCode.ArtDmx)

    # Assemble the packet
    packet = (
        ART_NET_HEADER
        + op_code
        + ART_NET_VERSION
        + sequence
        + physical
        + universe
        + dmx_length
        + dmx_data
    )

    return packet


def pack_nzs(
    universe15bit: int, sequence: int, start_code: int, dmx_data: bytes
) -> bytes:
    # Sequence, start code and universe
    seq = struct.pack("<B", sequence)
    code = struct.pack("<B", start_code)
    universe = struct.pack("<H", universe15bit)

    # size = 512
    size = len(dmx_data)

    if size > 512:
        raise ValueError("data too long")

    # Length of DMX data
    dmx_length = struct.pack(">H", size)

    # OpCode
    op_code = struct.pack("<H", OpCode.ArtNzs)

    # Assemble the packet
    packet = (
        ART_NET_HEADER
        + op_code
        + ART_NET_VERSION
        + seq
        + code
        + universe
        + dmx_length
        + dmx_data
    )

    return packet


def pack_trigger(key: int, subkey: int, data: bytes = b"") -> bytes:
    key_byte = struct.pack("<B", key)
    subkey_byte = struct.pack("<B", subkey)
    filler = struct.pack("<H", 0x0000)
    op_code = struct.pack("<H", OpCode.ArtTrigger)
    packet = (
        ART_NET_HEADER
        + op_code
        + ART_NET_VERSION
        + filler
        + ART_NET_OEM
        + key_byte
        + subkey_byte
        + data
    )

    return packet


def pack_sync() -> bytes:
    # Aux1 (Int8) and Aux1 (Int8) - Transmit as zero
    aux = b"\x00" * 2
    op_code = struct.pack("<H", OpCode.ArtSync)
    packet = ART_NET_HEADER + op_code + ART_NET_VERSION + aux

    return packet


def pack_poll_reply(
    ip: str = "0.0.0.0",
    port: int = 0,
    net_switch: int = 0,
    sub_switch: int = 0,
    ubea: int = 0,
    status1: int = 0xE3,
    short_name: str = "Art-Net Node",
    long_name: str = "Art-Net Node Long Name",
    node_report: str = "#0001 [0000] Node OK",
    num_ports: int = 1,
    port_types: list = [0x80, 0x00, 0x00, 0x00],
    good_input: list = [0, 0, 0, 0],
    good_output: list = [0x80, 0x00, 0x00, 0x00],
    sw_in: list = [0, 0, 0, 0],
    sw_out: list = [0, 0, 0, 0],
    sw_video: int = 0,
    sw_macro: int = 0,
    sw_remote: int = 0,
    style: int = 0,
    mac_address: bytes = b"\x00\x00\x00\x00\x00\x00",
    bind_ip: str = "0.0.0.0",
    bind_index: int = 1,
    status2: int = 0b11001110,
) -> bytes:
    """
    Constructs an ArtPollReply packet according to the Art-Net protocol.

    The packet consists of a fixed 239 bytes containing:
      - An 8-byte header ("Art-Net" + null)
      - A 2-byte OpCode (0x2100 for ArtPollReply, little-endian)
      - The node's IP address (4 bytes)
      - The Art-Net port (2 bytes, network order)
      - A 2-byte protocol version (little-endian)
      - Net and SubSwitch (1 byte each)
      - OEM code (2 bytes, little-endian)
      - Ubea version (1 byte)
      - Status1 (1 byte)
      - ESTA manufacturer code (2 bytes, little-endian)
      - Short name (18 bytes, ASCII, null padded)
      - Long name (64 bytes, ASCII, null padded)
      - Node report (64 bytes, ASCII, null padded)
      - Number of ports (1 byte)
      - Port types (4 bytes)
      - Good input (4 bytes)
      - Good output (4 bytes)
      - SwIn (4 bytes)
      - SwOut (4 bytes)
      - SwVideo, SwMacro, SwRemote (1 byte each)
      - 3 spare bytes
      - Style (1 byte)
      - MAC address (6 bytes)
      - Bind IP (4 bytes)
      - Bind Index (1 byte)
      - Status2 (1 byte)
      - 26 spare bytes
    """
    # OpCode for ArtPollReply (0x2100) packed as little-endian 16-bit integer
    op_code = struct.pack("<H", 0x2100)

    # IP address (4 bytes) converted from string to bytes
    ip_bytes = socket.inet_aton(ip)

    # Port (2 bytes) - Art-Net port is usually 0x1936; we pack in network order
    if port == 0:
        port = 0x1936

    port_bytes = struct.pack("!H", port)

    # NetSwitch and SubSwitch (1 byte each)
    net_switch_byte = struct.pack("B", net_switch)
    sub_switch_byte = struct.pack("B", sub_switch)

    # Ubea version (1 byte)
    ubea_byte = struct.pack("B", ubea)

    # Status1 (1 byte)
    status1_byte = struct.pack("B", status1)

    # Short name: 18 bytes ASCII, null-padded
    short_name_bytes = short_name.encode("ascii")[:18].ljust(18, b"\x00")

    # Long name: 64 bytes ASCII, null-padded
    long_name_bytes = long_name.encode("ascii")[:64].ljust(64, b"\x00")

    # Node report: 64 bytes ASCII, null-padded
    node_report_bytes = node_report.encode("ascii")[:64].ljust(64, b"\x00")

    # Number of ports (1 byte)
    num_ports_byte = struct.pack("!H", num_ports)

    # Ensure lists for port types, good input, and good output are 4 items long each
    port_types = (port_types + [0] * 4)[:4]
    good_input = (good_input + [0] * 4)[:4]
    good_output = (good_output + [0] * 4)[:4]
    sw_in = (sw_in + [0] * 4)[:4]
    sw_out = (sw_out + [0] * 4)[:4]

    port_types_bytes = bytes(port_types)
    good_input_bytes = bytes(good_input)
    good_output_bytes = bytes(good_output)
    sw_in_bytes = bytes(sw_in)
    sw_out_bytes = bytes(sw_out)

    # SwVideo, SwMacro, SwRemote (1 byte each)
    sw_video_byte = struct.pack("B", sw_video)
    sw_macro_byte = struct.pack("B", sw_macro)
    sw_remote_byte = struct.pack("B", sw_remote)

    # 3 spare bytes (all zeros)
    spare_bytes = b"\x00" * 3

    # Style (1 byte)
    style_byte = struct.pack("B", style)

    # MAC address: must be exactly 6 bytes (pad or truncate as needed)
    mac_address_bytes = mac_address[:6].ljust(6, b"\x00")

    # Bind IP (4 bytes)
    bind_ip_bytes = socket.inet_aton(bind_ip)

    # Bind Index (1 byte)
    bind_index_byte = struct.pack("B", bind_index)

    # Status2 (1 byte)
    status2_byte = struct.pack("B", status2)

    # Spare2: 26 bytes of zeros
    spare2_bytes = b"\x00" * 26

    packet = (
        ART_NET_HEADER
        + op_code
        + ip_bytes
        + port_bytes
        + ART_NET_VERSION
        + net_switch_byte
        + sub_switch_byte
        + ART_NET_OEM
        + ubea_byte
        + status1_byte
        + ART_NET_ESTA_MAN
        + short_name_bytes
        + long_name_bytes
        + node_report_bytes
        + num_ports_byte
        + port_types_bytes
        + good_input_bytes
        + good_output_bytes
        + sw_in_bytes
        + sw_out_bytes
        + sw_video_byte
        + sw_macro_byte
        + sw_remote_byte
        + spare_bytes
        + style_byte
        + mac_address_bytes
        + bind_ip_bytes
        + bind_index_byte
        + status2_byte
        + spare2_bytes
    )

    return packet


def pack_tod_request() -> bytes:
    """
    Packs an ArtTodRequest packet.

    The packet consists of:
      - Header: "Art-Net\x00" (8 bytes)
      - OpCode: 0x8000 (little-endian, 2 bytes)
      - Protocol Version: 2 bytes (big-endian)
      - Spare: 10 zero bytes
    Total length: 22 bytes.
    """
    op_code = struct.pack("<H", OpCode.ArtTodRequest)
    prot_ver_bytes = ART_NET_VERSION
    spare = b"\x00" * 10
    packet = ART_NET_HEADER + op_code + prot_ver_bytes + spare
    return packet


def pack_tod_data(config: dict[str, Any], tod_data: list[int]) -> bytes:
    """
    Packs an ArtTodData packet.
    """
    op_code = struct.pack("<H", OpCode.ArtTodData)
    data_length = len(tod_data)
    length_bytes = struct.pack(">H", data_length)
    packet = (
        ART_NET_HEADER
        + op_code
        + ART_NET_VERSION
        + b"\x01"  # RdmVer
        + b"\x01"  # Port
        + b"\x00" * 6  # Spare
        + b"\x01"  # BindIndex
        + struct.pack("B", config.get("net", 0))
        + b"\x00"  # TodFull
        + struct.pack(
            "B", config.get("sub", 0) * 16 + (config.get("universe", 0))
        )  # Address
        + length_bytes  # UidTotal
        + b"\x00"  # BlockCount
        + struct.pack("B", data_length)  # UidCount
        + b"".join(x.to_bytes(6, byteorder="big") for x in tod_data)
    )
    return packet


def pack_tod_control(command: int) -> bytes:
    """
    Packs an ArtTodControl packet.

    The packet consists of:
      - Header: "Art-Net\x00" (8 bytes)
      - OpCode: 0x8002 (little-endian, 2 bytes)
      - Protocol Version: 2 bytes (big-endian)
      - Command: 1 byte (control command)
      - Spare: 1 byte (zero)
    Total length: 14 bytes.
    """
    op_code = struct.pack("<H", OpCode.ArtTodControl)
    prot_ver_bytes = ART_NET_VERSION
    command_byte = struct.pack("<B", command)
    spare = b"\x00"
    packet = ART_NET_HEADER + op_code + prot_ver_bytes + command_byte + spare
    return packet


def pack_data(format_string, data):
    """
    Packs data into bytes based on a comma-separated format string.

    - Supports `[]` for lists (applies format to each element).
    - Automatically encodes strings to bytes.

    Args:
        format_string (str): Comma-separated struct format string, e.g., "I,H,[B],32s".
        data (tuple, list): Data matching the format.

    Returns:
        bytes: Packed binary data.
    """

    format_tokens = [token.strip() for token in format_string.split(",")]
    packed_bytes = bytearray()
    data_index = 0

    for token in format_tokens:
        array_match = re.match(r"\[(.*)\]", token)  # Check if it's an array format

        if array_match:
            fmt = array_match.group(1)  # Extract format inside []
            array_data = data[data_index]

            if not isinstance(array_data, (list, tuple)):
                raise ValueError(
                    f"Expected list/tuple for format [{fmt}], got {type(array_data)}"
                )

            for item in array_data:
                if isinstance(item, str) and "s" in fmt:
                    item = item.encode("utf-8")  # Convert strings to bytes
                packed_bytes.extend(struct.pack(fmt, item))

        else:
            if isinstance(data, str) and "s" in token:
                item = data.encode("utf-8")  # Convert string to bytes if needed
            else:
                if isinstance(data, (list, tuple)):
                    item = data[data_index]
                else:
                    item = data

            # Fix: Ensure a string is treated as a full value, not iterated
            if isinstance(item, str) and "s" in token:
                item = item.encode("utf-8")  # Convert string to bytes if needed

            packed_bytes.extend(struct.pack(token, item))

        data_index += 1

    return bytes(packed_bytes)


def unpack_data(format_string, packed_bytes):
    """
    Unpacks bytes into a tuple or list based on a comma-separated format string.

    - Supports `[]` for lists (applies format to each element).
    - Uses struct.unpack internally.

    Args:
        format_string (str): Comma-separated struct format string, e.g., "I,H,[B]".
        packed_bytes (bytes): The binary data to unpack.

    Returns:
        tuple: Unpacked data (or lists for array formats).
    """

    format_tokens = [token.strip() for token in format_string.split(",")]
    data = []
    offset = 0

    for token in format_tokens:
        array_match = match(r"\[(.*)\]", token)  # Check for array format

        if array_match:
            fmt = array_match.group(1)  # Extract format inside []
            fmt_size = struct.calcsize(fmt)  # Get size of each element
            array_length = (
                len(packed_bytes) - offset
            ) // fmt_size  # Calculate elements

            array_data = [
                struct.unpack_from(fmt, packed_bytes, offset + i * fmt_size)[0]
                for i in range(array_length)
            ]
            data.append(array_data)
            offset += array_length * fmt_size

        else:
            fmt_size = struct.calcsize(token)
            value = struct.unpack_from(token, packed_bytes, offset)[0]
            data.append(value)
            offset += fmt_size

    return tuple(data)


import json

from ArtNet.rdm import RdmParameterID


def serialize_device_info(device_info):
    """
    Converts DEVICE_INFO to a JSON-serializable format.
    - Converts RdmParameterID keys to their string names.
    """

    def custom_serializer(obj):
        if isinstance(obj, dict):
            return {
                k.name if isinstance(k, RdmParameterID) else k: custom_serializer(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [custom_serializer(v) for v in obj]
        elif isinstance(obj, tuple):
            return tuple(custom_serializer(v) for v in obj)  # Keep tuples as tuples
        elif isinstance(obj, RdmParameterID):
            return obj.name  # Convert Enum to string name instead of an integer
        return obj  # Return other types unchanged

    return json.dumps(custom_serializer(device_info), indent=2, separators=(",", ": "))


def deserialize_device_info(json_string):
    """
    Converts JSON back to a Python dictionary.
    - Converts RdmParameterID strings back to Enum objects.
    """

    def custom_deserializer(obj):
        if isinstance(obj, dict):
            new_dict = {}
            for k, v in obj.items():
                # Convert string back to RdmParameterID if it matches an Enum name
                if isinstance(k, str) and k in RdmParameterID.__members__:
                    k = RdmParameterID[k]
                new_dict[k] = custom_deserializer(v)
            return new_dict
        elif isinstance(obj, list):
            return [custom_deserializer(v) for v in obj]
        return obj

    return custom_deserializer(json.loads(json_string))


import yaml


def serialize_device_info_yaml(device_info):
    """
    Converts DEVICE_INFO to a YAML-serializable format.
    - Converts RdmParameterID keys to their string names.
    - Ensures the output is human-readable (avoids !!python/object).
    """

    def custom_serializer(obj):
        if isinstance(obj, dict):
            return {
                k.name if isinstance(k, RdmParameterID) else k: custom_serializer(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [custom_serializer(v) for v in obj]
        elif isinstance(obj, tuple):
            return tuple(custom_serializer(v) for v in obj)  # Keep tuples as tuples
        elif isinstance(obj, RdmParameterID):
            return obj.name  # Convert Enum to string
        return obj  # Return other types unchanged

    return yaml.dump(custom_serializer(device_info), default_flow_style=False)


def deserialize_device_info_yaml(yaml_string):
    """
    Loads YAML and converts RdmParameterID keys back into Enum objects.
    """

    def custom_deserializer(obj):
        if isinstance(obj, dict):
            return {
                (
                    RdmParameterID[k] if k in RdmParameterID.__members__ else k
                ): custom_deserializer(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [custom_deserializer(v) for v in obj]
        return obj

    return custom_deserializer(yaml.safe_load(yaml_string))
