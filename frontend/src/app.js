// Get runtime configuration
const runtimeConfig = ConfigAccessor.getRuntimeConfig();

// Configure marked for markdown parsing
if (typeof marked !== 'undefined') {
  marked.setOptions({
    gfm: true,              // GitHub Flavored Markdown
    breaks: true,           // Convert \n to <br>
    headerIds: false,       // Don't add IDs to headers
    mangle: false,          // Don't mangle email addresses
  });
}

const chat = document.getElementById("chat");
const form = document.getElementById("composer");
const promptInput = document.getElementById("prompt");
const statusBadge = document.getElementById("status");
const endpoint = window.AGENTCORE_ENDPOINT || "";
const wsSignEndpoint = window.WS_SIGN_ENDPOINT || "";
const maxAuthRetries = runtimeConfig.maxAuthRetries;

// Cookie utility functions
function setCookie(name, value, minutes) {
  const expirationMinutes = minutes || runtimeConfig.cookieExpirationMinutes;
  const date = new Date();
  date.setTime(date.getTime() + (expirationMinutes * 60 * 1000));
  const expires = "expires=" + date.toUTCString();
  document.cookie = name + "=" + value + ";" + expires + ";path=/";
}

function getCookie(name) {
  const nameEQ = name + "=";
  const cookies = document.cookie.split(';');
  for (let i = 0; i < cookies.length; i++) {
    let cookie = cookies[i];
    while (cookie.charAt(0) === ' ') {
      cookie = cookie.substring(1);
    }
    if (cookie.indexOf(nameEQ) === 0) {
      return cookie.substring(nameEQ.length, cookie.length);
    }
  }
  return null;
}

function handleRuntimeSessionId(sessionId) {
  if (!sessionId) {
    return;
  }
  
  const cookieName = "runtime_session_id";
  const existingSessionId = getCookie(cookieName);
  
  if (!existingSessionId) {
    // Cookie doesn't exist, create it
    setCookie(cookieName, sessionId, runtimeConfig.cookieExpirationMinutes);
    console.log("Runtime session ID stored in cookie:", sessionId);
  } else if (existingSessionId !== sessionId) {
    // Cookie exists but value is different, override it
    setCookie(cookieName, sessionId, runtimeConfig.cookieExpirationMinutes);
    console.log("Runtime session ID updated in cookie:", sessionId);
  }
  // If values are the same, do nothing
}

function addMessage(text, role) {
  const msg = document.createElement("div");
  msg.className = `message ${role}`;
  msg.innerHTML = renderMarkdown(text);
  chat.appendChild(msg);
  chat.scrollTop = chat.scrollHeight;
  return msg;
}

// Following code for window.addEventListener was provided
// by Adarsh on 20260211
// window.addEventListener('message', (event) => {
//   if (event.data.type === 'oauth_success') {
//     console.log('OAuth completed');
//     setStatus('Authenticated', true);
//   }
// });

function setStatus(text, ok = false) {
  statusBadge.textContent = text;
  statusBadge.style.color = ok ? "#67e8f9" : "#f8fafc";
  statusBadge.style.background = ok
    ? "rgba(34, 211, 238, 0.2)"
    : "rgba(148, 163, 184, 0.2)";
}

if (!endpoint && !wsSignEndpoint) {
  setStatus("Missing endpoint");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const prompt = promptInput.value.trim();
  if (!prompt || (!endpoint && !wsSignEndpoint)) {
    return;
  }

  addMessage(prompt, "user");
  promptInput.value = "";
  setStatus("Sending...", true);
  const pending = addMessage("Thinking...", "agent pending");

  try {
    if (wsSignEndpoint) {
      try {
        await streamViaWebSocket(prompt, pending);
      } catch (wsErr) {
        // Fallback to HTTP if WebSocket fails.
        await sendViaHttp(prompt, pending, 0);
      }
    } else {
      await sendViaHttp(prompt, pending, 0);
    }
    pending.classList.remove("pending");
    setStatus("Connected", true);
  } catch (err) {
    pending.innerHTML = renderMarkdown(`Network error: ${err}`);
    pending.classList.remove("pending");
    setStatus("Error");
  }
});

async function sendViaHttp(prompt, element, attempt) {
  const headers = {
    "Content-Type": "application/json",
  };

  // Get access token from MSAL if user is logged in
  try {
    const accessToken = await getAccessToken();
    if (accessToken && accessToken.accessToken) {
      headers["Authorization"] = `Bearer ${accessToken.accessToken}`;
      console.log("Added authorization token to request");
      console.log("Token (first 20 chars):", accessToken.accessToken.substring(0, 20) + "...");
      
      // Decode access token to see its claims
      try {
        const tokenParts = accessToken.accessToken.split('.');
        const payload = JSON.parse(atob(tokenParts[1]));
        console.log("Access token claims:", payload);
      } catch (e) {
        console.log("Could not decode access token:", e);
      }
      
      console.log("Token properties:", {
        scopes: accessToken.scopes,
        account: accessToken.account ? {
          username: accessToken.account.username,
          name: accessToken.account.name,
          homeAccountId: accessToken.account.homeAccountId,
          tenantId: accessToken.account.tenantId
        } : null,
        expiresOn: accessToken.expiresOn,
        tokenType: accessToken.tokenType,
        idToken: accessToken.idToken ? accessToken.idToken.substring(0, 20) + "..." : null,
        idTokenClaims: accessToken.idTokenClaims
      });
    }
  } catch (err) {
    console.log("No access token available (user may not be logged in):", err.message);
  }

  // Get runtime session ID from cookie if it exists
  const sessionId = getCookie("runtime_session_id");
  
  // Build request body with session ID
  const requestBody = { prompt };
  if (sessionId) {
    requestBody.runtime_session_id = sessionId;
    console.log("Sending runtime session ID in request body:", sessionId);
  } else {
    console.log("No runtime session ID found in cookie");
  }

  console.log("Sending request to:", endpoint);

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers,
      body: JSON.stringify(requestBody),
    });

    console.log("Response status:", response.status);

    if (!response.ok) {
      const errText = await response.text();
      addMessage(`Error: ${response.status} ${errText}`, "agent");
      setStatus("Error");
      return;
    }

    const data = await response.json();
    
    // Handle runtime session ID from response
    if (data.runtime_session_id) {
      handleRuntimeSessionId(data.runtime_session_id);
    }
    
    if (data.auth_url) {
      if (attempt >= maxAuthRetries) {
        element.innerHTML = renderMarkdown("Authorization required but failed after retries.");
        return;
      }
      await handleAuthFlow(data.auth_url, prompt, element, attempt + 1);
      return;
    }

    if (data.result) {
      await streamText(element, data.result);
    } else if (data.error) {
      element.innerHTML = renderMarkdown(`Error: ${data.error}`);
    } else {
      element.innerHTML = renderMarkdown("No response payload from agent.");
    }
  } catch (fetchError) {
    console.error("Fetch error details:", fetchError);
    throw fetchError;
  }
}

async function streamText(element, text) {
  const content = String(text);
  let buffer = "";
  for (let i = 0; i < content.length; i += 1) {
    buffer += content[i];
    element.innerHTML = renderMarkdown(buffer);
    chat.scrollTop = chat.scrollHeight;
    await new Promise((resolve) => setTimeout(resolve, 12));
  }
}

async function streamViaWebSocket(prompt, element) {
  const signResp = await fetch(wsSignEndpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ expires: 300, qualifier: "DEFAULT" }),
  });

  if (!signResp.ok) {
    const errText = await signResp.text();
    throw new Error(`Signer error: ${signResp.status} ${errText}`);
  }

  const signData = await signResp.json();
  if (!signData.wsUrl) {
    throw new Error("Signer returned no wsUrl");
  }

  return new Promise((resolve, reject) => {
    const ws = new WebSocket(signData.wsUrl);
    let buffer = "";
    let done = false;

    ws.onopen = () => {
      ws.send(JSON.stringify({ prompt }));
    };

    ws.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch (_err) {
        return;
      }

      if (message.type === "delta") {
        buffer += message.data || "";
        element.innerHTML = renderMarkdown(buffer);
        chat.scrollTop = chat.scrollHeight;
      } else if (message.type === "done") {
        done = true;
        ws.close();
        resolve();
      } else if (message.type === "error") {
        done = true;
        ws.close();
        reject(new Error(message.error || "Stream error"));
      }
    };

    ws.onerror = () => {
      if (!done) {
        reject(new Error("WebSocket error"));
      }
    };

    ws.onclose = () => {
      if (!done) {
        resolve();
      }
    };
  });
}

async function handleAuthFlow(authUrl, prompt, element, attempt) {
  // Define openPopup function first
  const openPopup = () =>
    window.open(
      authUrl,
      "agentcoreAuth",
      "popup=yes,width=520,height=720,noopener,noreferrer"
    );

  // Attempt to open popup immediately
  const popup = openPopup();
  
  if (popup) {
    // Popup opened successfully - automatic flow
    element.innerHTML = renderMarkdown("Authorizing...");
    popup.focus();
    await waitForPopupClose(popup);
    element.innerHTML = renderMarkdown("Authorization complete. Retrying request...");
    await sendViaHttp(prompt, element, attempt);
  } else {
    // Popup was blocked - show fallback UI
    element.innerHTML = renderMarkdown(
      "Authorization required. If the popup is blocked, click the link below to continue."
    );

    const button = document.createElement("button");
    button.type = "button";
    button.className = "auth-button";
    button.textContent = "Open sign-in popup (recommended)";

    const link = document.createElement("a");
    link.href = authUrl;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "Open in new tab (fallback)";
    link.className = "auth-link";

    element.appendChild(document.createElement("br"));
    element.appendChild(button);
    element.appendChild(document.createElement("br"));
    element.appendChild(link);

    button.addEventListener("click", async () => {
      const popup = openPopup();
      if (!popup) {
        element.innerHTML = renderMarkdown(
          "Popup was blocked. Use the fallback link above."
        );
        return;
      }
      popup.focus();
      await waitForPopupClose(popup);
      element.innerHTML = renderMarkdown("Authorization complete. Retrying request...");
      await sendViaHttp(prompt, element, attempt);
    });
  }
}

function waitForPopupClose(popup) {
  return new Promise((resolve) => {
    const timer = window.setInterval(() => {
      if (popup.closed) {
        window.clearInterval(timer);
        resolve();
      }
    }, 500);
  });
}

function renderMarkdown(input) {
  // Handle null, undefined, or empty input gracefully
  if (input === null || input === undefined || input === '') {
    return '';
  }

  // Convert input to string safely
  let markdownText;
  try {
    markdownText = String(input);
  } catch (error) {
    // If String() fails (e.g., object with broken toString), return empty string
    console.error('Error converting input to string:', error);
    return '';
  }

  // Check if marked and DOMPurify are available
  if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
    console.error('marked or DOMPurify not loaded');
    return markdownText;
  }

  try {
    // Parse markdown to HTML using marked
    const rawHtml = marked.parse(markdownText);

    // Sanitize HTML using DOMPurify with configured whitelist
    const sanitizedHtml = DOMPurify.sanitize(rawHtml, {
      ALLOWED_TAGS: [
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'br', 'strong', 'em', 'del', 's',
        'a', 'code', 'pre',
        'ul', 'ol', 'li',
        'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'blockquote', 'hr'
      ],
      ALLOWED_ATTR: ['href', 'target', 'rel', 'align'],
      ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|[^a-z]|[a-z+.-]+(?:[^a-z+.\-:]|$))/i
    });

    return sanitizedHtml;
  } catch (error) {
    console.error('Error rendering markdown:', error);
    return markdownText;
  }
}

