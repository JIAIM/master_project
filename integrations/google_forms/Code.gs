/**
 * EduTest → Google Форми: отримує тест у JSON від бекенду й створює форму в режимі тесту.
 * Налаштування — README.md поруч.
 */

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);

    const secret = PropertiesService.getScriptProperties().getProperty('EDUTEST_SECRET');
    if (!secret || data.secret !== secret) {
      return json_({ ok: false, error: 'Невірний секрет — перевірте EDUTEST_SECRET у скрипті та GOOGLE_APPS_SCRIPT_SECRET у .env' });
    }
    if (!data.questions || !data.questions.length) {
      return json_({ ok: false, error: 'У тесті немає питань' });
    }

    const form = FormApp.create(data.title || 'Тест EduTest');
    if (data.description) form.setDescription(data.description);
    form.setIsQuiz(true);
    form.setCollectEmail(true);
    form.setLimitOneResponsePerUser(false);   // true вимагає входу студента в Google-акаунт
    form.setShowLinkToRespondAgain(false);
    form.setAllowResponseEdits(false);

    data.questions.forEach(function (q) {
      const item = q.type === 'multiple_choice' ? form.addCheckboxItem() : form.addMultipleChoiceItem();
      item.setTitle(q.text).setRequired(true).setPoints(q.points || 1);
      item.setChoices(q.options.map(function (o) { return item.createChoice(o.text, !!o.is_correct); }));
      if (q.explanation) {
        const feedback = FormApp.createFeedback().setText(q.explanation).build();
        item.setFeedbackForCorrect(feedback);
        item.setFeedbackForIncorrect(feedback);
      }
    });

    // Викладач стає редактором; якщо email не Google-акаунт — редагування за посиланням
    let shared = 'editor';
    try {
      if (!data.teacher_email) throw new Error('no email');
      form.addEditor(data.teacher_email);
    } catch (err) {
      DriveApp.getFileById(form.getId()).setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.EDIT);
      shared = 'link';
    }

    return json_({
      ok: true,
      form_id: form.getId(),
      edit_url: form.getEditUrl(),
      respond_url: form.getPublishedUrl(),
      shared: shared,
    });
  } catch (error) {
    return json_({ ok: false, error: String(error) });
  }
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
