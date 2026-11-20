import { useState } from "react";
import { getOperatorToken, setOperatorToken } from "../operatorToken";

// The operator token is sent as X-Operator-Token on every write call.
export function Settings() {
  const [token, setToken] = useState(getOperatorToken);
  return (
    <details className="settings">
      <summary>Settings</summary>
      <label className="small">
        Operator token (sent with Send, Cancel and Reset)
        <input
          type="password"
          autoComplete="off"
          value={token}
          onChange={(e) => {
            setToken(e.target.value);
            setOperatorToken(e.target.value);
          }}
        />
      </label>
    </details>
  );
}
