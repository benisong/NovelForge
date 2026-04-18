import { apiUrl, loginUrl } from './url';

export async function fetchStream(url, body, onMessage, signal) {
  try {
    const response = await fetch(apiUrl(url), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      signal
    });

    if (response.status === 401) {
      window.location.href = loginUrl();
      throw new Error('未登录');
    }

    if (!response.ok) {
      let errMsg = `HTTP Error ${response.status}`;
      try {
        const errorData = await response.json();
        if (errorData.error) errMsg = errorData.error;
      } catch (e) {}
      throw new Error(errMsg);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let fullText = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunkStr = decoder.decode(value, { stream: true });
      const lines = chunkStr.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const dataStr = line.slice(6).trim();
          if (dataStr === '[DONE]') {
             break; // Stream finished
          }
          if (dataStr) {
             try {
                const dataObj = JSON.parse(dataStr);
                if (dataObj.error) {
                   throw new Error(dataObj.error);
                }
                if (dataObj.content) {
                   fullText += dataObj.content;
                   if (typeof onMessage === 'function') {
                      onMessage(fullText);
                   }
                }
             } catch(e) {
                // Not JSON or parse error, ignore partial chunk lines
             }
          }
        }
      }
    }
    return fullText;
  } catch (error) {
    if (error.name === 'AbortError') {
      console.log('Stream aborted manually');
    }
    throw error;
  }
}
