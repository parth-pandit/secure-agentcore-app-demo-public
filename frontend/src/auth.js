// Browser check variables - can be removed if not supporting IE
const ua = window.navigator.userAgent;
const msie = ua.indexOf("MSIE ");
const msie11 = ua.indexOf("Trident/");
const isIE = msie > 0 || msie11 > 0;

let accountId = "";

// Create the main myMSALObj instance
// configuration parameters are located at authConfig.js
const myMSALObj = new msal.PublicClientApplication(msalConfig);

myMSALObj.initialize().then(() => {
    // Handle redirect response after login
    myMSALObj.handleRedirectPromise().then(handleResponse).catch(err => {
        console.error("Error handling redirect:", err);
    });
    
    // Check if user is already logged in on page load
    updateUIState();
})

function updateUIState() {
    const currentAccounts = myMSALObj.getAllAccounts();
    const signInButton = document.getElementById('signin');
    const signOutButton = document.getElementById('signout');
    const userInfoDiv = document.getElementById('user-info');
    const loginPrompt = document.getElementById('login-prompt');
    const composer = document.getElementById('composer');
    const chat = document.getElementById('chat');
    
    if (currentAccounts && currentAccounts.length > 0) {
        // User is logged in
        if (signInButton) signInButton.style.display = 'none';
        if (signOutButton) signOutButton.style.display = 'inline-block';
        if (userInfoDiv) {
            userInfoDiv.style.display = 'inline-block';
            userInfoDiv.innerHTML = `Hello, ${currentAccounts[0].name}!`;
        }
        // Show chat and composer, hide login prompt
        if (loginPrompt) loginPrompt.style.display = 'none';
        if (composer) composer.style.display = 'flex';
        if (chat) chat.style.display = 'flex';
        console.log("User is logged in:", currentAccounts[0].username);
    } else {
        // User is not logged in
        if (signInButton) signInButton.style.display = 'inline-block';
        if (signOutButton) signOutButton.style.display = 'none';
        if (userInfoDiv) {
            userInfoDiv.style.display = 'none';
            userInfoDiv.innerHTML = '';
        }
        // Hide chat and composer, show login prompt
        if (loginPrompt) loginPrompt.style.display = 'block';
        if (composer) composer.style.display = 'none';
        if (chat) chat.style.display = 'none';
        console.log("User is not logged in");
    }
}

function selectAccount() {
    const currentAccounts = myMSALObj.getAllAccounts();

    if (!currentAccounts || currentAccounts.length === 0) {
        updateUIState();
        return;
    } else if (currentAccounts.length > 1) {
        console.warn("Multiple accounts detected.");
        accountId = currentAccounts[0].homeAccountId;
        myMSALObj.setActiveAccount(currentAccounts[0]);
    } else if (currentAccounts.length === 1) {
        accountId = currentAccounts[0].homeAccountId;
        myMSALObj.setActiveAccount(currentAccounts[0]);
    }
    updateUIState();
}

function displayUserInfo(account) {
    accountId = account.homeAccountId;
    updateUIState();
}

function handleResponse(resp) {
    console.log("Login response:", resp);
    if (resp !== null) {
        accountId = resp.account.homeAccountId;
        myMSALObj.setActiveAccount(resp.account);
        displayUserInfo(resp.account);
    } else {
        selectAccount();
    } 
}

async function signIn() {
    console.log("Starting redirect login...");
    return myMSALObj.loginRedirect(loginRequest);
}

function signOut() {
    const account = myMSALObj.getActiveAccount() || myMSALObj.getAllAccounts()[0];
    
    if (!account) {
        console.error("No account found to sign out");
        return;
    }
    
    const logoutRequest = {
        account: account,
        postLogoutRedirectUri: window.location.origin
    };
    
    console.log("Signing out...");
    myMSALObj.logoutRedirect(logoutRequest);
}

// Get access token for API calls
async function getAccessToken() {
    const account = myMSALObj.getActiveAccount();
    if (!account) {
        throw new Error("No active account. Please sign in.");
    }

    return await myMSALObj.acquireTokenSilent({
        ...loginRequest,
        account: account
    }).catch(async (error) => {
        console.log("Silent token acquisition failed:", error);
        if (error instanceof msal.InteractionRequiredAuthError) {
            // Fallback to redirect if silent acquisition fails
            console.log("Acquiring token using redirect");
            return myMSALObj.acquireTokenRedirect(loginRequest);
        } else {
            throw error;
        }
    });
}