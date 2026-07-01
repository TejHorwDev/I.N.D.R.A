import 'package:flutter_test/flutter_test.dart';
import 'package:record/record.dart';

import 'helpers/fake_record_platform.dart';
import 'helpers/test_utils.dart';

void main() {
  late FakeRecordPlatform fake;
  late AudioRecorder recorder;

  setUp(() async {
    fake = FakeRecordPlatform();
    RecordPlatform.instance = fake;
    recorder = AudioRecorder();
    await pump();
  });

  tearDown(() async {
    try {
      await recorder.dispose();
    } catch (_) {}
  });

  group('isRecording', () {
    test('returns true when platform reports recording', () async {
      fake.isRecordingResult = true;
      expect(await recorder.isRecording(), isTrue);
    });

    test('returns false when platform reports not recording', () async {
      fake.isRecordingResult = false;
      expect(await recorder.isRecording(), isFalse);
    });

    test('calls platform isRecording', () async {
      await recorder.isRecording();
      expect(fake.calls, contains('isRecording'));
    });
  });

  group('isPaused', () {
    test('returns true when platform reports paused', () async {
      fake.isPausedResult = true;
      expect(await recorder.isPaused(), isTrue);
    });

    test('returns false when platform reports not paused', () async {
      fake.isPausedResult = false;
      expect(await recorder.isPaused(), isFalse);
    });
  });

  group('hasPermission', () {
    test('returns true when permission granted', () async {
      fake.hasPermissionResult = true;
      expect(await recorder.hasPermission(), isTrue);
    });

    test('returns false when permission denied', () async {
      fake.hasPermissionResult = false;
      expect(await recorder.hasPermission(), isFalse);
    });

    test('defaults request parameter to true', () async {
      await recorder.hasPermission();
      expect(fake.lastHasPermissionRequest, isTrue);
    });

    test('passes request=false to platform', () async {
      await recorder.hasPermission(request: false);
      expect(fake.lastHasPermissionRequest, isFalse);
    });
  });

  group('listInputDevices', () {
    test('returns empty list by default', () async {
      expect(await recorder.listInputDevices(), isEmpty);
    });

    test('returns devices from platform', () async {
      fake.devicesResult = const [
        InputDevice(id: 'mic1', label: 'Built-in Microphone'),
        InputDevice(id: 'mic2', label: 'USB Headset'),
      ];
      final devices = await recorder.listInputDevices();
      expect(devices, hasLength(2));
      expect(devices.first.id, 'mic1');
      expect(devices.last.label, 'USB Headset');
    });
  });

  group('getAmplitude', () {
    test('returns amplitude from platform', () async {
      fake.amplitudeResult = Amplitude(current: -20.0, max: -5.0);
      final amp = await recorder.getAmplitude();
      expect(amp.current, -20.0);
      expect(amp.max, -5.0);
    });

    test('calls platform getAmplitude', () async {
      await recorder.getAmplitude();
      expect(fake.calls, contains('getAmplitude'));
    });
  });

  group('isEncoderSupported', () {
    test('returns true when encoder is supported', () async {
      fake.isEncoderSupportedResult = true;
      expect(await recorder.isEncoderSupported(AudioEncoder.aacLc), isTrue);
    });

    test('returns false when encoder is not supported', () async {
      fake.isEncoderSupportedResult = false;
      expect(await recorder.isEncoderSupported(AudioEncoder.opus), isFalse);
    });

    test('passes encoder to platform', () async {
      await recorder.isEncoderSupported(AudioEncoder.flac);
      expect(fake.lastCheckedEncoder, AudioEncoder.flac);
    });
  });
}
