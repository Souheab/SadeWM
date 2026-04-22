// SPDX-License-Identifier: MIT
//
// Thin glue layer between QLightDM::Greeter and the QML frontend.
//
// The QLightDM Qt5 library already exposes a fully-featured ``Greeter``
// QObject with a signals/slots API, so in principle QML could drive it
// directly.  In practice a couple of the signals carry nested-enum
// arguments (``QLightDM::Greeter::PromptType`` / ``MessageType``) that
// QML struggles to introspect, and we want an unambiguous place to
// record the "currently expected response kind" so the password field
// can switch between echoed and masked input.  ``GreeterBridge``
// forwards those signals as plain QML-friendly integers/strings and
// keeps a tiny bit of state for the UI.

#pragma once

#include <QObject>
#include <QString>

namespace QLightDM { class Greeter; }

class GreeterBridge : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString lastPrompt   READ lastPrompt   NOTIFY stateChanged)
    Q_PROPERTY(QString lastMessage  READ lastMessage  NOTIFY stateChanged)
    Q_PROPERTY(bool    promptSecret READ promptSecret NOTIFY stateChanged)
    Q_PROPERTY(bool    awaitingResponse READ awaitingResponse NOTIFY stateChanged)
    Q_PROPERTY(QString hostname     READ hostname     CONSTANT)

public:
    explicit GreeterBridge(QLightDM::Greeter *greeter, QObject *parent = nullptr);

    QString lastPrompt()     const { return m_lastPrompt; }
    QString lastMessage()    const { return m_lastMessage; }
    bool    promptSecret()   const { return m_promptSecret; }
    bool    awaitingResponse() const { return m_awaitingResponse; }
    QString hostname()       const;

public slots:
    // Begin authentication for ``username`` (empty = manual / prompt).
    void authenticate(const QString &username);
    // Provide a response to the most recent prompt.
    void respond(const QString &response);
    // Abort the current authentication attempt.
    void cancel();
    // Once ``authenticated`` is true, start the chosen session.
    // Empty session => use the default session hint.
    bool startSession(const QString &session);

signals:
    void stateChanged();
    void promptReceived(const QString &text, bool secret);
    void messageReceived(const QString &text, bool error);
    void authenticationComplete(bool success);

private slots:
    void onShowPrompt(QString text, int type);
    void onShowMessage(QString text, int type);
    void onAuthenticationComplete();

private:
    QLightDM::Greeter *m_greeter;
    QString m_lastPrompt;
    QString m_lastMessage;
    bool    m_promptSecret     = true;
    bool    m_awaitingResponse = false;
};
