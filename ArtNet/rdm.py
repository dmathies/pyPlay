import struct
from enum import IntEnum

from .helper import ArtNetFieldDict


class RdmCommandClass(IntEnum):

  RdmDiscoveryCommand = 0x10
  RdmDiscoveryCommandResponse = 0x11
  RdmGetCommand = 0x20
  RdmGetCommandResponse = 0x21
  RdmSetCommand = 0x30
  RdmSetCommandResponse = 0x31


class RdmParameterID(IntEnum):
  # Discovery Commands
  RdmParamDiscUniqueBranch = 0x0001
  RdmParamDiscMute = 0x0002
  RdmParamDiscUnMute = 0x0003

  RdmParamProxiedDevices = 0x0010
  RdmParamProxiedDeviceCount = 0x0011

  RdmParamCommsStatus = 0x0015

  RdmParamQueuedMessage = 0x0020
  RdmParamStatusMessages = 0x0030
  RdmParamStatusIdDescription = 0x0031
  RdmParamClearStatusId = 0x0032
  RdmParamSubDeviceStatusReportThreshold = 0x0033

  RdmParamSupportedParameters = 0x0050
  RdmParamParameterDescription = 0x0051

  RdmParamDeviceInfo = 0x0060
  RdmParamProductDetailIdList = 0x0070
  RdmParamDeviceModelDescription = 0x0080
  RdmParamManufacturerLabel = 0x0081
  RdmParamDeviceLabel = 0x0082
  RdmParamFactoryDefaults = 0x0090

  RdmParamLanguageCapabilities = 0x00A0
  RdmParamLanguage = 0x00B0

  RdmParamSoftwareVersionLabel = 0x00C0
  RdmParamBootSoftwareVersionId = 0x00C1
  RdmParamBootSoftwareVersionLabel = 0x00C2

  RdmParamDmxPersonality = 0x00E0
  RdmParamDmxPersonalityDescription = 0x00E1
  RdmParamDmxStartAddress = 0x00F0

  RdmParamSlotInfo = 0x0120
  RdmParamSlotDescription = 0x0121
  RdmParamDefaultSlotValue = 0x0122

  RdmParamDmxBlockAddress = 0x0140
  RdmParamDmxFailMode = 0x0141
  RdmParamDmxStartupMode = 0x0142

  RdmParamSensorDefinition = 0x0200
  RdmParamSensorValue = 0x0201
  RdmParamRecordSensors = 0x0202

  RdmParamDimmerInfo = 0x0340
  RdmParamMinimumLevel = 0x0341
  RdmParamMaximumLevel = 0x0342
  RdmParamCurve = 0x0343
  RdmParamCurveDescription = 0x0344
  RdmParamOutputResponseTime = 0x0345
  RdmParamOutputResponseTimeDescription = 0x0346
  RdmParamModulationFrequency = 0x0347
  RdmParamModulationFrequencyDescription = 0x0348

  RdmParamDeviceHours = 0x0400
  RdmParamLampHours = 0x0401
  RdmParamLampStrikes = 0x0402
  RdmParamLampState = 0x0403
  RdmParamLampOnMode = 0x0404
  RdmParamDevicePowerCycles = 0x0405

  RdmParamBurnIn = 0x0440

  RdmParamDisplayInvert = 0x0500
  RdmParamDisplayLevel = 0x0501
  RdmParamPanInvert = 0x0600
  RdmParamTiltInvert = 0x0601
  RdmParamPanTiltSwap = 0x0602
  RdmParamRealTimeClock = 0x0603

  RdmParamLockPin = 0x0640
  RdmParamLockState = 0x0641
  RdmParamLockStateDescription = 0x0642

  RdmParamListInterfaces = 0x0700
  RdmParamInterfaceLabel = 0x0701
  RdmParamInterfaceHardwareAddressType1 = 0x0702
  RdmParamIpv4DhcpMode = 0x0703
  RdmParamIpv4ZeroconfMode = 0x0704
  RdmParamIpv4CurrentAddress = 0x0705
  RdmParamIpv4StaticAddress = 0x0706
  RdmParamInterfaceRenewDhcp = 0x0707
  RdmParamInterfaceReleaseDhcp = 0x0708
  RdmParamInterfaceApplyConfiguration = 0x0709
  RdmParamIpv4DefaultRoute = 0x070A
  RdmParamDnsIpv4NameServer = 0x070B
  RdmParamDnsHostname = 0x070C
  RdmParamDnsDomainName = 0x070D

  RdmParamComponentScope = 0x0800
  RdmParamSearchDomain = 0x0801
  RdmParamTcpCommsStatus = 0x0802
  RdmParamBrokerStatus = 0x0803

  RdmParamEndpointList = 0x0900
  RdmParamEndpointListChange = 0x0901
  RdmParamIdentifyEndpoint = 0x0902
  RdmParamEndpointToUniverse = 0x0903
  RdmParamEndpointMode = 0x0904
  RdmParamEndpointLabel = 0x0905
  RdmParamRdmTrafficEnable = 0x0906
  RdmParamDiscoveryState = 0x0907
  RdmParamBackgroundDiscovery = 0x0908
  RdmParamEndpointTiming = 0x0909
  RdmParamEndpointTimingDescription = 0x090A
  RdmParamEndpointResponders = 0x090B
  RdmParamEndpointResponderListChange = 0x090C
  RdmParamBindingControlFields = 0x090D
  RdmParamBackgroundQueuedStatusPolicy = 0x090E
  RdmParamBackgroundQueuedStatusPolicyDescription = 0x090F

  RdmParamIdentifyDevice = 0x1000
  RdmParamResetDevice = 0x1001
  RdmParamPowerState = 0x1010
  RdmParamPerformSelftest = 0x1020
  RdmParamSelfTestDescription = 0x1021
  RdmParamCapturePreset = 0x1030
  RdmParamPresetPlayback = 0x1031
  RdmParamIdentifyMode = 0x1040
  RdmParamPresetInfo = 0x1041
  RdmParamPresetStatus = 0x1042
  RdmParamPresetMergemode = 0x1043
  RdmParamPowerOnSelfTest = 0x1044

  RdmParamMyDimmer = 0x8000
  RdmParamMyPlaybackNumber = 0x8001

def parse_rdm(data: bytes) -> ArtNetFieldDict:
  if len(data) < 24:
    return None

  reply = dict(
      ProtVer=struct.unpack("<H", data[10:12])[0],
      RdmVer=data[12],
      FifoAvail=data[19],
      FifoMax=data[20],
      Net=data[21]&0x7f,
      Command=data[22],
      Address=data[23],
      RdmPacket=data[24:],
      RdmSubStartCode=data[24],
      RdmMessageLength=data[25],
      RdmDestUID=int.from_bytes(data[26:32], byteorder='big'),
      RdmSourceUID=int.from_bytes(data[32:38], byteorder='big'),
      RdmTransactioNumber=data[38],
      RdmPort=data[39],
      RdmMessageCount=data[40],
      RdmSubDevice=struct.unpack("<H", data[41:43])[0],
      RdmCommand=RdmCommandClass(data[43]),
      RdmParameterId=RdmParameterID(struct.unpack(">H", data[44:46])[0]),
      RdmParameterDataLength=data[46],
      RdmParameterData=data[47:]
  )

  return reply

def pack_rdm(unpacket: ArtNetFieldDict) -> bytes:

  # Assemble the packet
  packet = (((
      b'\x01' # Sub-START Code
      + struct.pack("B", unpacket["RdmParameterDataLength"]+24)
      + int.to_bytes(unpacket["RdmDestUID"], length=6, byteorder='big'))
      + int.to_bytes(unpacket["RdmSourceUID"], length=6, byteorder='big'))
      + struct.pack("B", (unpacket["RdmTransactioNumber"] +1) & 0xff)
      + b'\x00' # RESPONSE_TYPE_ACK
      + b'\x00' # Message Count
      + b'\x00'*2 # Sub-Device
      + struct.pack("B", unpacket["RdmCommand"])
      + struct.pack(">H", unpacket["RdmParameterId"])
      + struct.pack("B", unpacket["RdmParameterDataLength"])
      + unpacket["RdmParameterData"]  # Append parameter data
  )

  return packet

