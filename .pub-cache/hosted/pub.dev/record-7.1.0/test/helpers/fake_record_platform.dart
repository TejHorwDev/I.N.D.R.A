import 'dart:async';
import 'dart:typed_data';

import 'package:record/record.dart';

class FakeRecordPlatform extends RecordPlatform {
  final List<String> calls = [];
  String? lastCreatedId;
  String? lastStartPath;
  AudioEncoder? lastCheckedEncoder;
  bool? lastHasPermissionRequest;

  bool isRecordingResult = false;
  bool isPausedResult = false;
  bool hasPermissionResult = true;
  bool isEncoderSupportedResult = true;
  String? stopResult = '/recording.m4a';
  Amplitude amplitudeResult = Amplitude(current: -40.0, max: -10.0);
  List<InputDevice> devicesResult = const [];
  Exception? createException;

  final _stateControllers = <String, StreamController<RecordState>>{};
  StreamController<Uint8List>? byteStreamCtrl;

  /// Emits a state on the recorder whose ID was last registered via create().
  void emitState(RecordState state) {
    if (lastCreatedId != null) {
      _stateControllers[lastCreatedId]?.add(state);
    }
  }

  /// Emits an error on the recorder whose ID was last registered via create().
  void emitError(Object error) {
    if (lastCreatedId != null) {
      _stateControllers[lastCreatedId]?.addError(error);
    }
  }

  @override
  Future<void> create(String recorderId) async {
    calls.add('create');
    lastCreatedId = recorderId;
    _stateControllers[recorderId] = StreamController<RecordState>.broadcast();
    if (createException != null) throw createException!;
  }

  @override
  Future<void> start(
    String recorderId,
    RecordConfig config, {
    required String path,
  }) async {
    calls.add('start');
    lastStartPath = path;
  }

  @override
  Future<Stream<Uint8List>> startStream(
    String recorderId,
    RecordConfig config,
  ) async {
    calls.add('startStream');
    byteStreamCtrl = StreamController<Uint8List>.broadcast();
    return byteStreamCtrl!.stream;
  }

  @override
  Future<String?> stop(String recorderId) async {
    calls.add('stop');
    return stopResult;
  }

  @override
  Future<void> pause(String recorderId) async => calls.add('pause');

  @override
  Future<void> resume(String recorderId) async => calls.add('resume');

  @override
  Future<bool> isRecording(String recorderId) async {
    calls.add('isRecording');
    return isRecordingResult;
  }

  @override
  Future<bool> isPaused(String recorderId) async {
    calls.add('isPaused');
    return isPausedResult;
  }

  @override
  Future<bool> hasPermission(String recorderId, {bool request = true}) async {
    calls.add('hasPermission');
    lastHasPermissionRequest = request;
    return hasPermissionResult;
  }

  @override
  Future<void> cancel(String recorderId) async => calls.add('cancel');

  @override
  Future<void> dispose(String recorderId) async {
    calls.add('dispose');
    await _stateControllers[recorderId]?.close();
    _stateControllers.remove(recorderId);
  }

  @override
  Future<Amplitude> getAmplitude(String recorderId) async {
    calls.add('getAmplitude');
    return amplitudeResult;
  }

  @override
  Future<bool> isEncoderSupported(
    String recorderId,
    AudioEncoder encoder,
  ) async {
    calls.add('isEncoderSupported');
    lastCheckedEncoder = encoder;
    return isEncoderSupportedResult;
  }

  @override
  Future<List<InputDevice>> listInputDevices(String recorderId) async {
    calls.add('listInputDevices');
    return devicesResult;
  }

  @override
  Stream<RecordState> onStateChanged(String recorderId) {
    calls.add('onStateChanged');
    return _stateControllers[recorderId]!.stream;
  }

  @override
  void setOnConfigChanged(
    String recorderId,
    void Function(RecordConfig config)? handler,
  ) {
    calls.add('setOnConfigChanged');
  }
}
