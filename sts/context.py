"""Bounded per-connection token-count cache; never silently discard the world or current input."""
import hashlib
from collections import OrderedDict


class ContextBudget:
    def __init__(self):
        self.counts = OrderedDict()

    async def fit(self, client, messages, limit, output_tokens, port, headers):
        messages = list(messages)
        # UTF-8 bytes are a conservative token upper bound for this byte-fallback tokenizer.
        # Reserve 64 tokens per chat wrapper and 128 for template/response markers.
        remaining = limit - output_tokens - 128
        byte_upper = sum(len(m['content'].encode('utf-8')) + 64 for m in messages)
        if byte_upper <= remaining:
            return messages
        counts = []
        for message in messages:
            content = message['content']
            key = hashlib.sha256(content.encode('utf-8')).digest()
            if key not in self.counts:
                response = await client.post(f'http://127.0.0.1:{port}/tokenize', headers=headers,
                    json={'content': content, 'add_special': False, 'parse_special': False})
                response.raise_for_status()
                self.counts[key] = len(response.json()['tokens'])
                if len(self.counts) > 64:
                    self.counts.popitem(last=False)
            self.counts.move_to_end(key)
            counts.append(self.counts[key] + 64)
        while sum(counts) > remaining:
            if len(messages) <= 2:
                raise ValueError('世界設定と質問が長すぎます。Markdownまたは質問を短くしてください。')
            del messages[1:3]
            del counts[1:3]
        return messages
