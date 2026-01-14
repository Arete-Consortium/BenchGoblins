import React, { useState } from 'react';
import {
  View,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAppStore } from '../stores/appStore';

export function ChatInput() {
  const [text, setText] = useState('');
  const { sendMessage, isLoading } = useAppStore();

  const handleSend = async () => {
    if (!text.trim() || isLoading) return;

    const message = text.trim();
    setText('');
    await sendMessage(message);
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={100}
    >
      <View style={styles.container}>
        <TextInput
          style={styles.input}
          placeholder="Ask about a player..."
          placeholderTextColor="#64748b"
          value={text}
          onChangeText={setText}
          onSubmitEditing={handleSend}
          returnKeyType="send"
          editable={!isLoading}
          multiline
        />
        <TouchableOpacity
          style={[styles.sendButton, (!text.trim() || isLoading) && styles.disabledButton]}
          onPress={handleSend}
          disabled={!text.trim() || isLoading}
        >
          {isLoading ? (
            <ActivityIndicator color="#ffffff" size="small" />
          ) : (
            <Ionicons name="send" size={20} color="#ffffff" />
          )}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    padding: 12,
    paddingBottom: 24,
    backgroundColor: '#0f0f1a',
    borderTopWidth: 1,
    borderTopColor: '#1a1a2e',
    gap: 8,
  },
  input: {
    flex: 1,
    backgroundColor: '#1a1a2e',
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 12,
    fontSize: 16,
    color: '#e2e8f0',
    maxHeight: 120,
  },
  sendButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#4f46e5',
    alignItems: 'center',
    justifyContent: 'center',
  },
  disabledButton: {
    backgroundColor: '#374151',
  },
});
