"""Read-only inbox through the stock modem API. Never sends or deletes SMS."""
from control import api, ControlError

def messages():
 raw=api('/api/v2/sms/list.json?n=200')
 if not isinstance(raw.get('msg'),list):raise ControlError('Служба СМС не вернула список сообщений.')
 result=[]
 for item in raw['msg']:
  if not isinstance(item,dict) or item.get('direction') not in (0,'0'):continue
  identifier=item.get('id')
  if type(identifier) is not int or identifier<0:continue
  result.append({'id':identifier,'sender':str(item.get('sender') or item.get('from') or 'Неизвестный отправитель')[:100],
                 'time':str(item.get('timestamp') or item.get('send_at') or '')[:64],
                 'text':str(item.get('content') or '')[:6000]})
 return sorted(result,key=lambda m:m['id'],reverse=True),len(raw['msg'])>=200

def execute(operation,args):
 if not isinstance(args,dict):raise ControlError('Некорректные параметры СМС.')
 if operation=='sms_list':
  if set(args)-{'before'}:raise ControlError('Неизвестные параметры СМС.')
  before=args.get('before')
  if before is not None and (type(before) is not int or before<0):raise ControlError('Некорректная страница СМС.')
 elif operation=='sms_read':
  if set(args)!={'id'} or type(args['id']) is not int or args['id']<0:raise ControlError('Некорректное сообщение.')
 else:raise ControlError('Операция СМС не поддерживается.')
 rows,limited=messages()
 if operation=='sms_read':
  message=next((m for m in rows if m['id']==args['id']),None)
  if message is None:raise ControlError('Сообщение больше недоступно. Обнови список.')
  return {'sms_message':message}
 eligible=[m for m in rows if before is None or m['id']<before]
 page=eligible[:10]
 return {'sms':{'messages':[{k:v for k,v in m.items() if k!='text'}|{'preview':m['text'][:140]} for m in page],
                'next':page[-1]['id'] if len(eligible)>10 else None,'limited':limited}}
