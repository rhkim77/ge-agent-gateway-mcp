# frozen_string_literal: true

# ==============================================================================
# Step 6: Verify 4 Red-Team Security Scenarios & BigQuery Audit Correlation
# ==============================================================================
def step_6_ge_e2e_audit_check(handles:, maximum_score:, resources:)
  ret_hash = {
    done: false,
    score: 0,
    message: 'error_message',
    student_message: 'error_message'
  }

  begin
    logging = handles['project_0.LoggingV2'] || handles[:LoggingV2]
    storage = handles['project_0.StorageV1'] || handles[:StorageV1]
    project_id = (resources['project_0']['project_id'] rescue nil) ||
                 (resources[:project_0][:project_id] rescue nil) ||
                 (logging.project rescue nil) ||
                 (storage.project rescue nil)

    verified = false

    if logging && project_id
      begin
        lab_start_time = Time.at(Time.now.to_i - 14_400).utc.iso8601
        custom_filter = [
          "timestamp>\"#{lab_start_time}\"",
          '(protoPayload.serviceName="discoveryengine.googleapis.com" OR protoPayload.serviceName="bigquery.googleapis.com")',
          '(protoPayload.methodName:"StreamAssist" OR protoPayload.methodName:"Assist" OR protoPayload.resourceName:"cymbal_ge_governance_audit")'
        ].join(' AND ')

        request = Google::Apis::LoggingV2::ListLogEntriesRequest.new
        request.resource_names = ["projects/#{project_id}"]
        request.filter = custom_filter

        entries = logging.list_entry_log_entries(request)&.entries || []
        verified = true if entries.count.positive?
      rescue StandardError
        # Fallback to StorageV1 below
      end
    end

    if !verified && storage && project_id
      begin
        bucket_name = "#{project_id}-ge-agw-state"
        objects = storage.list_objects(bucket_name)&.items || []
        object_names = objects.map(&:name)
        if object_names.any? { |name| name.include?('step5_security_scenarios_report.json') } &&
           object_names.any? { |name| name.include?('step6_audit_correlation_report.json') }
          verified = true
        end
      rescue StandardError
        # Ignore fallback error
      end
    end

    if verified
      ret_hash = {
        done: true,
        score: maximum_score,
        message: 'success',
        student_message: 'success'
      }
    end
  rescue StandardError => e
    ret_hash[:message] = e.message
    ret_hash[:student_message] = 'error_message'
  end

  ret_hash
end
