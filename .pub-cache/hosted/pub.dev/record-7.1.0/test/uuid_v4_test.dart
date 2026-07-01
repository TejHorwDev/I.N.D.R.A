import 'package:flutter_test/flutter_test.dart';
import 'package:record/src/util/uuid_v4.dart';

void main() {
  group('UuidV4', () {
    final uuidPattern = RegExp(
      r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    );

    test('matches UUID v4 format', () {
      expect(UuidV4.generate(), matches(uuidPattern));
    });

    test('version nibble is always 4', () {
      for (var i = 0; i < 100; i++) {
        final uuid = UuidV4.generate();
        expect(uuid[14], equals('4'));
      }
    });

    test('variant nibble is always 8, 9, a, or b', () {
      const validVariants = {'8', '9', 'a', 'b'};
      for (var i = 0; i < 100; i++) {
        final uuid = UuidV4.generate();
        expect(validVariants, contains(uuid[19]));
      }
    });

    test('length is 36 characters', () {
      expect(UuidV4.generate().length, equals(36));
    });

    test('hyphens are at positions 8, 13, 18, 23', () {
      final uuid = UuidV4.generate();
      for (final pos in [8, 13, 18, 23]) {
        expect(uuid[pos], equals('-'));
      }
    });

    test('generates unique values', () {
      final uuids = List.generate(1000, (_) => UuidV4.generate()).toSet();
      expect(uuids.length, equals(1000));
    });
  });
}
