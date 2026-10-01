(() => {
  const box = document.getElementById('status-messages');
  let displayed = [];
  async function refreshStatusMessages() {
    try {
      const response = await fetch('/status-messages', {cache: 'no-store', signal: AbortSignal.timeout(15000)});
      if (!response.ok) return;
      const messages = await response.json();
      const following = box.scrollTop + box.clientHeight >= box.scrollHeight - 1;
      // A shorter or changed prefix means the server has restarted.
      if (messages.length < displayed.length || displayed.some((message, i) =>
        message.source !== messages[i].source || message.message !== messages[i].message)) {
        box.replaceChildren();
        displayed = [];
      }
      for (const message of messages.slice(displayed.length)) {
        const line = document.createElement('div');
        line.textContent = `[${message.source}] ${message.message}`;
        line.title = line.textContent;
        box.append(line);
      }
      displayed = messages;
      if (following) box.scrollTop = box.scrollHeight;
    } catch (error) {
      // Keep the current history visible while the server is unreachable.
    } finally {
      window.setTimeout(refreshStatusMessages, 2000);
    }
  }
  refreshStatusMessages();
})();
