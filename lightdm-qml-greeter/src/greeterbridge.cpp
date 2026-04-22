// SPDX-License-Identifier: MIT
#include "greeterbridge.h"

#include <QLightDM/Greeter>
#include <QDebug>

using QLightDM::Greeter;

GreeterBridge::GreeterBridge(Greeter *greeter, QObject *parent)
    : QObject(parent), m_greeter(greeter)
{
    // Qt5 quirk: the nested-enum arguments on these signals can't be
    // referenced through the string-based SIGNAL/SLOT macros without
    // also listing the fully-qualified enum name (and slot with
    // matching type).  Using the functor overload sidesteps that - we
    // translate the enum to ``int`` inside the lambda and keep QML
    // free of lightdm-specific types.
    connect(m_greeter, &Greeter::showPrompt,
            this, [this](QString text, Greeter::PromptType type) {
                onShowPrompt(text, static_cast<int>(type));
            });
    connect(m_greeter, &Greeter::showMessage,
            this, [this](QString text, Greeter::MessageType type) {
                onShowMessage(text, static_cast<int>(type));
            });
    connect(m_greeter, &Greeter::authenticationComplete,
            this,      &GreeterBridge::onAuthenticationComplete);
}

QString GreeterBridge::hostname() const
{
    return m_greeter ? m_greeter->hostname() : QString();
}

void GreeterBridge::authenticate(const QString &username)
{
    m_lastPrompt.clear();
    m_lastMessage.clear();
    m_awaitingResponse = false;
    emit stateChanged();
    m_greeter->authenticate(username);
}

void GreeterBridge::respond(const QString &response)
{
    m_awaitingResponse = false;
    emit stateChanged();
    m_greeter->respond(response);
}

void GreeterBridge::cancel()
{
    m_greeter->cancelAuthentication();
    m_lastPrompt.clear();
    m_awaitingResponse = false;
    emit stateChanged();
}

bool GreeterBridge::startSession(const QString &session)
{
    if (!m_greeter->isAuthenticated()) {
        qWarning() << "startSession called before authentication completed";
        return false;
    }
    return m_greeter->startSessionSync(session);
}

void GreeterBridge::onShowPrompt(QString text, int type)
{
    m_lastPrompt = text;
    m_promptSecret = (type == Greeter::PromptTypeSecret);
    m_awaitingResponse = true;
    emit stateChanged();
    emit promptReceived(text, m_promptSecret);
}

void GreeterBridge::onShowMessage(QString text, int type)
{
    m_lastMessage = text;
    const bool error = (type == Greeter::MessageTypeError);
    emit stateChanged();
    emit messageReceived(text, error);
}

void GreeterBridge::onAuthenticationComplete()
{
    const bool ok = m_greeter->isAuthenticated();
    m_awaitingResponse = false;
    emit stateChanged();
    emit authenticationComplete(ok);
}
