import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Contract Tests against mezo-shared-client fixtures', () {
    test('Parses chat response fixture', () {
      final file = File('../mezo-shared-client/contract-fixtures/chat-response.json');
      final content = file.readAsStringSync();
      final Map<String, dynamic> data = jsonDecode(content);

      expect(data['status'], 'success');
      expect(data['provider'], 'gemini');
      expect(data['result']['text'], 'Hello! I am MEZO AI.');
    });

    test('Parses kill switch status fixture', () {
      final file = File('../mezo-shared-client/contract-fixtures/kill-switch-status.json');
      final content = file.readAsStringSync();
      final Map<String, dynamic> data = jsonDecode(content);

      expect(data['armed'], true);
      expect(data['disarmed_at'], isNull);
      expect(data['disarmed_by'], isNull);
    });
  });
}
