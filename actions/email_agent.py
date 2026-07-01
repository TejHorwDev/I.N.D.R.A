import urllib.parse
import os

def email_agent(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Drafts an email by opening the system's default mail client with pre-filled fields.
    """
    to = parameters.get("to", "")
    subject = parameters.get("subject", "")
    body = parameters.get("body", "")
    
    if not body:
        return "You must provide an email body."
        
    try:
                                   
        query_params = {}
        if subject:
            query_params['subject'] = subject
        if body:
            query_params['body'] = body
            
        mailto_url = f"mailto:{to}"
        if query_params:
            mailto_url += "?" + urllib.parse.urlencode(query_params, quote_via=urllib.parse.quote)
            
        os.startfile(mailto_url)
        return "Email draft opened in your default mail client. Please review and send."
    except Exception as e:
        return f"Failed to draft email: {e}"
